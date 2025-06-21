#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ロリポップサーバー向け自動デプロイツール - デプロイ実行
Gitの差分を基にFTPでファイルをアップロードします
"""

import os
import sys
import json
import ftplib
import argparse
import subprocess
from pathlib import Path, PurePosixPath
from typing import List, Dict, Optional, Union
import logging
from datetime import datetime
import time

class LolipopDeployTool:
    def __init__(self, config_file: str = "deploy_config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.setup_logging()
        self.deploy_log_file = "deploy_history.json"
        
    def setup_logging(self):
        """ログ設定"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('deploy.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_config(self) -> Dict:
        """設定ファイルを読み込み"""
        if not os.path.exists(self.config_file):
            self.logger.error(f"設定ファイル '{self.config_file}' が見つかりません")
            self.logger.error("まず 'python init.py' を実行してセットアップを完了してください")
            sys.exit(1)
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"設定ファイルの読み込みに失敗: {e}")
            sys.exit(1)
    
    def get_app_config(self, app_name: str) -> Optional[Dict]:
        """指定されたアプリの設定を取得"""
        for app in self.config['apps']:
            if app['name'] == app_name:
                return app
        return None
    
    def get_last_deploy_commit(self, app_name: str) -> Optional[str]:
        """前回デプロイ時のコミットハッシュを取得"""
        if not os.path.exists(self.deploy_log_file):
            return None
        
        try:
            with open(self.deploy_log_file, 'r', encoding='utf-8') as f:
                deploy_log = json.load(f)
            return deploy_log.get(app_name, {}).get('last_commit')
        except:
            return None
    
    def save_deploy_commit(self, app_name: str, commit_hash: str):
        """デプロイ時のコミットハッシュを保存"""
        deploy_log = {}
        if os.path.exists(self.deploy_log_file):
            try:
                with open(self.deploy_log_file, 'r', encoding='utf-8') as f:
                    deploy_log = json.load(f)
            except:
                pass
        
        if app_name not in deploy_log:
            deploy_log[app_name] = {}
        
        deploy_log[app_name]['last_commit'] = commit_hash
        deploy_log[app_name]['last_deploy'] = datetime.now().isoformat()
        
        with open(self.deploy_log_file, 'w', encoding='utf-8') as f:
            json.dump(deploy_log, f, indent=2, ensure_ascii=False)
    
    def get_current_commit(self, local_path: str) -> str:
        """現在のコミットハッシュを取得"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=local_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Gitコマンドの実行に失敗: {e}")
            sys.exit(1)
    
    def get_changed_files(self, local_path: str, from_commit: Optional[str] = None) -> Dict[str, List[str]]:
        """
        変更されたファイルのリストをステータス別に取得
        :return: {'upload': [...], 'delete': [...]}
        """
        try:
            if from_commit:
                # 前回デプロイから現在までの変更ファイル
                cmd = ['git', 'diff', '--name-status', f"{from_commit}..HEAD"]
                result = subprocess.run(
                    cmd,
                    cwd=local_path,
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding='utf-8'
                )
                
                added_modified_files = []
                deleted_files = []
                
                for line in result.stdout.splitlines():
                    if not line:
                        continue
                    
                    parts = line.split('\t')
                    status = parts[0]
                    
                    if status.startswith('R'): # Renamed
                        _, old_path, new_path = parts
                        deleted_files.append(old_path)
                        added_modified_files.append(new_path)
                    elif status.startswith('D'): # Deleted
                        deleted_files.append(parts[1])
                    else: # Added, Modified, etc.
                        added_modified_files.append(parts[1])

                return {
                    "upload": self.filter_files(added_modified_files),
                    "delete": self.filter_files(deleted_files)
                }
            else:
                # 全ファイル（初回デプロイ）
                cmd = ['git', 'ls-files']
                result = subprocess.run(cmd, cwd=local_path, capture_output=True, text=True, check=True, encoding='utf-8')
                files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
                return {"upload": self.filter_files(files), "delete": []}

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Gitコマンドの実行に失敗: {e}")
            sys.exit(1)
    
    def filter_files(self, files: List[str]) -> List[str]:
        """除外パターンに基づいてファイルをフィルタリング"""
        exclude_patterns = self.config.get('exclude_patterns', [])
        filtered_files = []
        
        for file in files:
            should_exclude = False
            for pattern in exclude_patterns:
                if pattern.startswith('*'):
                    # 拡張子パターン
                    if file.endswith(pattern[1:]):
                        should_exclude = True
                        break
                else:
                    # パス含有パターン
                    if pattern in file:
                        should_exclude = True
                        break
            
            if not should_exclude:
                filtered_files.append(file)
        
        return filtered_files
    
    def connect_ftp(self) -> ftplib.FTP:
        """FTP接続を確立"""
        try:
            ftp = ftplib.FTP()
            ftp.connect(
                self.config['ftp']['host'], 
                timeout=self.config.get('timeout', 30)
            )
            ftp.login(
                self.config['ftp']['username'],
                self.config['ftp']['password']
            )
            ftp.set_pasv(True)  # パッシブモード
            self.logger.info("FTP接続が確立されました")
            return ftp
        except Exception as e:
            self.logger.error(f"FTP接続に失敗: {e}")
            sys.exit(1)
    
    def ensure_remote_directory(self, ftp: ftplib.FTP, remote_path: str):
        """リモートディレクトリが存在しない場合は作成"""
        try:
            ftp.cwd(remote_path)
        except ftplib.error_perm:
            # ディレクトリが存在しない場合は作成
            dirs = remote_path.strip('/').split('/')
            current_path = ''
            
            for directory in dirs:
                if directory:
                    current_path += '/' + directory
                    try:
                        ftp.cwd(current_path)
                    except ftplib.error_perm:
                        try:
                            ftp.mkd(current_path)
                            self.logger.info(f"ディレクトリを作成: {current_path}")
                        except ftplib.error_perm as e:
                            self.logger.warning(f"ディレクトリ作成に失敗: {current_path} - {e}")
                            break

    def upload_file(self, ftp: ftplib.FTP, local_file: Union[Path, str], remote_file: str, retries: int = 3, delay: int = 5) -> bool:
        """ファイルをアップロード（リトライ機能付き）"""
        last_exception = None
        for attempt in range(retries):
            try:
                # 最初の試行でのみディレクトリと上書き設定を確認
                if attempt == 0:
                    # リモートディレクトリを確保
                    remote_dir = os.path.dirname(remote_file)
                    if remote_dir and remote_dir != '/':
                        self.ensure_remote_directory(ftp, remote_dir)

                    # 上書き設定を確認
                    overwrite = self.config.get('overwrite', True)
                    if not overwrite:
                        try:
                            ftp.size(remote_file)
                            self.logger.info(f"上書き禁止のためスキップ: {remote_file}")
                            return True
                        except ftplib.error_perm:
                            pass

                # ファイルをアップロード
                with open(local_file, 'rb') as f:
                    ftp.storbinary(f'STOR {remote_file}', f)

                self.logger.info(f"アップロード完了: {local_file} -> {remote_file}")
                return True

            except Exception as e:
                last_exception = e
                self.logger.warning(f"アップロード失敗 (試行 {attempt + 1}/{retries}): {local_file} - {e}")
                if attempt < retries - 1:
                    self.logger.info(f"{delay}秒後にリトライします...")
                    time.sleep(delay)

        # 全てのリトライが失敗した場合
        self.logger.error(f"アップロードに失敗: {local_file} -> {remote_file} - {last_exception}")
        return False
    
    def delete_remote_file(self, ftp: ftplib.FTP, remote_file: str, retries: int = 3, delay: int = 5) -> bool:
        """リモートファイルを削除（リトライ機能付き）"""
        last_exception = None
        for attempt in range(retries):
            try:
                ftp.delete(remote_file)
                self.logger.info(f"削除完了: {remote_file}")
                return True
            except ftplib.error_perm as e:
                if "550" in str(e): # No such file or directory
                    self.logger.warning(f"削除スキップ (存在しない): {remote_file}")
                    return True # 目的は達成されているのでTrue
                last_exception = e
                self.logger.warning(f"削除失敗 (試行 {attempt + 1}/{retries}): {remote_file} - {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
        self.logger.error(f"削除に失敗: {remote_file} - {last_exception}")
        return False

    def _clear_dir_recursively(self, ftp: ftplib.FTP, path: str):
        """指定されたパス（ファイルまたはディレクトリ）を再帰的に削除する（内部ヘルパー）"""
        try:
            # ディレクトリに移動
            ftp.cwd(path)
            # 中身を一覧取得
            for name in ftp.nlst():
                if name in ('.', '..'):
                    continue
                # 再帰呼び出し
                self._clear_dir_recursively(ftp, name)
            # 親ディレクトリに戻る
            ftp.cwd('..')
            # 空になったディレクトリを削除
            ftp.rmd(path)
        except ftplib.error_perm:
            # ディレクトリでなければファイルとして削除
            ftp.delete(path)
        except Exception as e:
            self.logger.error(f"クリア処理中にエラー ({path}): {e}")
            raise

    def clear_remote_directory(self, ftp: ftplib.FTP, remote_dir: str) -> bool:
        """リモートディレクトリの中身をすべて削除するが、ディレクトリ自体は残す"""
        self.logger.info(f"リモートディレクトリの内容をクリアします: {remote_dir}")
        original_cwd = ftp.pwd()
        try:
            ftp.cwd(remote_dir)
            for name in ftp.nlst():
                if name in ('.', '..'):
                    continue
                self._clear_dir_recursively(ftp, name)
            return True
        except ftplib.error_perm as e:
            if "550" in str(e): # ディレクトリが存在しない
                self.logger.info(f"ディレクトリが存在しないためクリア不要: {remote_dir}")
                return True
            self.logger.error(f"ディレクトリのクリア中にエラー: {remote_dir} - {e}")
            return False
        finally:
            # 必ず元のディレクトリに戻る
            ftp.cwd(original_cwd)

    def deploy(self, app_name: str, all: bool = False, dry_run: bool = False):
        """デプロイを実行。dry_run=Trueの場合は、実際の転送は行わない。"""
        # アプリ設定を取得
        app_config = self.get_app_config(app_name)
        if not app_config:
            self.logger.error(f"アプリ '{app_name}' の設定が見つかりません")
            return False
        
        local_path = app_config['local_path']
        remote_path = app_config['remote_path']
        
        # ローカルパスの存在確認
        if not os.path.exists(local_path):
            self.logger.error(f"ローカルパスが存在しません: {local_path}")
            return False
        
        # Gitリポジトリの確認
        if not os.path.exists(os.path.join(local_path, '.git')):
            self.logger.error(f"Gitリポジトリではありません: {local_path}")
            return False
        
        # 現在のコミットハッシュを取得
        current_commit = self.get_current_commit(local_path)
        self.logger.info(f"現在のコミット: {current_commit}")
        
        # 前回デプロイのコミットハッシュを取得
        last_deploy_commit = self.get_last_deploy_commit(app_name)
        
        if last_deploy_commit:
            self.logger.info(f"前回デプロイのコミット: {last_deploy_commit}")
            if last_deploy_commit == current_commit and not all:
                self.logger.info("変更がないため、デプロイをスキップします")
                return True
        
        # アップロード対象のGit管理ファイルを取得
        # 'all' フラグが指定された場合、または初回デプロイの場合は全ファイルを取得
        # そうでなければ、前回デプロイからの差分ファイルを取得
        changes = self.get_changed_files(local_path, None if all or not last_deploy_commit else last_deploy_commit)
        files_to_upload = set(changes["upload"])
        files_to_delete = set(changes["delete"])
        
        # 初回デプロイまたは強制デプロイの場合のログ
        if all or not last_deploy_commit:
            self.logger.info("初回デプロイまたは強制デプロイです")
            files_to_delete = set() # 強制デプロイの場合は削除は行わない

        # 'always_deploy_files' の処理
        always_deploy_paths = app_config.get('always_deploy_files', [])
        dirs_to_clear = []
        if always_deploy_paths:
            self.logger.info(f"[{app_name}] 'always_deploy_files' を処理します...")
            for path_str in always_deploy_paths:
                full_path = Path(local_path) / path_str
                if not full_path.exists():
                    self.logger.warning(f"  - スキップ (存在しない): {path_str}")
                    continue

                if full_path.is_dir():
                    self.logger.info(f"  - フォルダを処理: {path_str}")
                    remote_dir_to_clear = (PurePosixPath(remote_path) / path_str).as_posix()
                    dirs_to_clear.append(remote_dir_to_clear)
                    
                    # Gitの削除リストからこのディレクトリ配下のファイルを削除
                    path_prefix = Path(path_str).as_posix() + '/'
                    files_to_delete = {f for f in files_to_delete if not f.startswith(path_prefix)}
                    
                    # アップロードリストにフォルダ内のファイルを追加
                    for file_path in full_path.rglob('*'):
                        if file_path.is_file():
                            relative_path = file_path.relative_to(local_path)
                            files_to_upload.add(relative_path.as_posix())
                elif full_path.is_file():
                    self.logger.info(f"  - ファイルを追加: {path_str}")
                    files_to_upload.add(Path(path_str).as_posix())

        files_to_upload_list = sorted(list(files_to_upload))
        files_to_delete_list = sorted(list(files_to_delete))

        if not files_to_upload_list and not files_to_delete_list and not dirs_to_clear:
            self.logger.info("変更されたファイルがありません。")
            # 変更がない場合でも、Gitの差分が除外ファイルのみだった場合を考慮し、コミットハッシュを更新する
            if last_deploy_commit != current_commit:
                self.save_deploy_commit(app_name, current_commit)
                self.logger.info("デプロイ対象のファイルはありませんでしたが、コミットハッシュを更新しました。")
            return True

        # 処理内容のサマリーを表示
        self.logger.info("--- デプロイ内容の確認 ---")
        if dirs_to_clear:
            self.logger.info(f"クリア対象ディレクトリ数: {len(dirs_to_clear)}")
            for d in dirs_to_clear:
                self.logger.info(f"  - [クリア] {d}")
        if files_to_delete_list:
            self.logger.info(f"削除対象ファイル数: {len(files_to_delete_list)}")
            for file in files_to_delete_list:
                self.logger.info(f"  - [削除] {file}")
        if files_to_upload_list:
            self.logger.info(f"アップロード対象ファイル数: {len(files_to_upload_list)}")
            for file in files_to_upload_list:
                self.logger.info(f"  - [アップロード] {file}")

        # ドライランモード
        if dry_run:
            self.logger.info("--- ドライランモードのため、ここで処理を終了します ---")
            return True

        # 実際のデプロイ
        ftp = self.connect_ftp()
        try:
            upload_success_count = 0
            delete_success_count = 0
            total_fail_count = 0

            # 1. ディレクトリをクリア
            for remote_dir in dirs_to_clear:
                self.clear_remote_directory(ftp, remote_dir)

            # 2. ファイルを削除
            if files_to_delete_list:
                self.logger.info(f"ファイルを削除します: {len(files_to_delete_list)}件")
                for file in files_to_delete_list:
                    remote_file = (PurePosixPath(remote_path) / file).as_posix()
                    if self.delete_remote_file(ftp, remote_file):
                        delete_success_count += 1
                    else:
                        total_fail_count += 1
            
            # 3. ファイルをアップロード
            if files_to_upload_list:
                self.logger.info(f"ファイルをアップロードします: {len(files_to_upload_list)}件")
                for file in files_to_upload_list:
                    local_file = Path(local_path) / file
                    remote_file = (PurePosixPath(remote_path) / file).as_posix()
                    
                    if os.path.exists(local_file):
                        if self.upload_file(ftp, local_file, remote_file):
                            upload_success_count += 1
                        else:
                            total_fail_count += 1
                    else:
                        self.logger.warning(f"ローカルファイルが存在しません: {local_file}")
                        total_fail_count += 1
            
            self.logger.info(f"デプロイ完了: アップロード成功 {upload_success_count}件, 削除成功 {delete_success_count}件, 失敗 {total_fail_count}件")
            
            if total_fail_count == 0:
                self.save_deploy_commit(app_name, current_commit)
                self.logger.info("デプロイ情報を保存しました")
            
            return total_fail_count == 0
        finally:
            ftp.quit()

    def list_apps(self):
        """設定されているアプリ一覧を表示"""
        print("設定されているアプリ:")
        for app in self.config['apps']:
            print(f"  - {app['name']}: {app['local_path']} -> {app['remote_path']}")
        print(f"\n使用例: python deploy.py --app {self.config['apps'][0]['name']}")

def main():
    parser = argparse.ArgumentParser(description='ロリポップサーバー向け自動デプロイツール - デプロイ実行')
    parser.add_argument('--app', '-a', help='デプロイ対象のアプリ名')
    parser.add_argument('--config', '-c', default='deploy_config.json', help='設定ファイルのパス')
    parser.add_argument('--all', '-A', action='store_true', help='強制デプロイ（全ファイル）')
    parser.add_argument('--list', '-l', action='store_true', help='アプリ一覧を表示')
    parser.add_argument('--dry-run', '-d', action='store_true', help='デプロイを実行せずに、対象ファイル一覧を表示')
    
    args = parser.parse_args()
    
    # デプロイツールを初期化
    deploy_tool = LolipopDeployTool(args.config)
    
    if args.list:
        deploy_tool.list_apps()
        return
    
    if not args.app:
        print("エラー: --app でアプリ名を指定してください")
        print("利用可能なアプリ:")
        deploy_tool.list_apps()
        parser.print_help()
        sys.exit(1)
    
    # デプロイを実行
    success = deploy_tool.deploy(args.app, args.all, args.dry_run)
    
    if args.dry_run:
        sys.exit(0)

    if success:
        print("デプロイが正常に完了しました")
        sys.exit(0)
    else:
        print("デプロイでエラーが発生しました")
        sys.exit(1)

if __name__ == '__main__':
    main()