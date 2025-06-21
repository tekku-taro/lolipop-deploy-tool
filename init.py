#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ロリポップサーバー向け自動デプロイツール - セットアップ
初期設定ファイルの作成とFTP接続テストを行います
"""

import os
import sys
import json
import ftplib
import argparse
from typing import Dict
import logging
from pathlib import Path

class DeploySetup:
    def __init__(self, config_file: str = "deploy_config.json"):
        self.config_file = config_file
        self.setup_logging()
    
    def setup_logging(self):
        """ログ設定"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)
    
    def create_config_interactive(self):
        """対話型で設定ファイルを作成"""
        self.logger.info("ロリポップデプロイツールのセットアップを開始します")
        
        # FTP設定の入力
        print("\n=== FTP接続設定 ===")
        ftp_host = input("FTPホスト名 [ftp.lolipop.jp]: ").strip() or "ftp.lolipop.jp"
        ftp_username = input("FTPユーザー名: ").strip()
        if not ftp_username:
            self.logger.error("FTPユーザー名は必須です")
            return False
        
        ftp_password = input("FTPパスワード: ").strip()
        if not ftp_password:
            self.logger.error("FTPパスワードは必須です")
            return False
        
        # アプリ設定の入力
        print("\n=== アプリケーション設定 ===")
        apps = []
        
        while True:
            print(f"\n--- アプリ {len(apps) + 1} の設定 ---")
            app_name = input("アプリ名: ").strip()
            if not app_name:
                if len(apps) == 0:
                    self.logger.error("最低1つのアプリを設定してください")
                    continue
                else:
                    break
            
            local_path = input("ローカルパス (例: C:\\xampp\\htdocs\\my-app): ").strip()
            if not local_path:
                self.logger.error("ローカルパスは必須です")
                continue
            
            remote_path = input("リモートパス (例: /my-app): ").strip()
            if not remote_path:
                self.logger.error("リモートパスは必須です")
                continue
            
            # パスの正規化
            local_path = os.path.normpath(local_path)
            if not remote_path.startswith('/'):
                remote_path = '/' + remote_path
            
            # このアプリで常にデプロイするファイル/フォルダの設定
            print(f"\n--- [{app_name}] 常にデプロイするファイル/フォルダ設定 ---")
            print("Git管理外だが常にデプロイしたいものがあれば、このアプリのローカルパスからの相対パスで入力してください。")
            print("例: .env や dist (入力なしで終了)")
            app_always_deploy_files = []
            while True:
                path_to_deploy = input(f"ファイル/フォルダ ({len(app_always_deploy_files) + 1}個目): ").strip()
                if not path_to_deploy:
                    break
                app_always_deploy_files.append(path_to_deploy)

            apps.append({
                "name": app_name,
                "local_path": local_path,
                "remote_path": remote_path,
                "always_deploy_files": app_always_deploy_files
            })
            
            # 追加するかの確認
            add_more = input("\n他のアプリも設定しますか？ [y/N]: ").strip().lower()
            if add_more not in ['y', 'yes']:
                break

        print("\n=== デプロイ設定 ===")
        overwrite_input = input("既存のファイルを上書きしますか？ [Y/n]: ").strip().lower()
        overwrite = overwrite_input not in ['n', 'no']

        # 設定ファイルの作成
        config = {
            "ftp": {
                "host": ftp_host,
                "username": ftp_username,
                "password": ftp_password
            },
            "apps": apps,
            "overwrite": overwrite,
            "exclude_patterns": [
                ".git",
                ".gitignore",
                "__pycache__",
                "*.pyc",
                "*.pyo",
                ".DS_Store",
                "Thumbs.db",
                ".env", # .envは通常除外、ユーザーが常にデプロイしたい場合はalways_deploy_filesで指定
                ".env.local",
                "deploy_config.json",
                "deploy.log",
                "deploy_history.json", 
                "*.tmp",
                "*.log",
                ".vscode",
                ".idea",
                "*.swp",
                "*.swo"
            ],
            "timeout": 30
        }
        
        # 設定ファイルを保存
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.logger.info(f"設定ファイル '{self.config_file}' を作成しました")
            return config
        except Exception as e:
            self.logger.error(f"設定ファイルの作成に失敗: {e}")
            return False
    
    def load_config(self) -> Dict:
        """設定ファイルを読み込み"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"設定ファイルの読み込みに失敗: {e}")
            return None
    
    def test_ftp_connection(self, config: Dict) -> bool:
        """FTP接続テスト"""
        self.logger.info("FTP接続をテストしています...")
        
        try:
            ftp = ftplib.FTP()
            ftp.connect(
                config['ftp']['host'], 
                timeout=config.get('timeout', 30)
            )
            ftp.login(
                config['ftp']['username'],
                config['ftp']['password']
            )
            ftp.set_pasv(True)
            
            # サーバー情報を取得
            welcome_msg = ftp.getwelcome()
            self.logger.info("FTP接続テスト成功")
            self.logger.info(f"サーバー応答: {welcome_msg}")
            
            ftp.quit()
            return True
            
        except Exception as e:
            self.logger.error(f"FTP接続テスト失敗: {e}")
            return False
    
    def validate_local_paths(self, config: Dict) -> bool:
        """ローカルパスの存在確認"""
        self.logger.info("ローカルパスを確認しています...")
        
        all_valid = True
        for app in config['apps']:
            app_name = app['name']
            local_path = app['local_path']
            
            if not os.path.exists(local_path):
                self.logger.warning(f"[{app_name}] ローカルパスが存在しません: {local_path}")
                all_valid = False
                continue
            
            git_path = os.path.join(local_path, '.git')
            if not os.path.exists(git_path):
                self.logger.warning(f"[{app_name}] Gitリポジトリではありません: {local_path}")
                all_valid = False
                continue
            
            self.logger.info(f"[{app_name}] パス確認OK: {local_path}")
        
        return all_valid
    
    def create_gitignore_entry(self):
        """deploy_config.json を .gitignore に追加"""
        gitignore_path = ".gitignore"
        entry = "deploy_config.json"
        
        # .gitignore が存在するかチェック
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if entry not in content:
                with open(gitignore_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n# デプロイツール設定ファイル\n{entry}\ndeploy.log\ndeploy_history.json\n") 
                self.logger.info(".gitignore に設定ファイルを追加しました")
            else:
                self.logger.info(".gitignore に既に設定済みです")
        else:
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write(f"# デプロイツール設定ファイル\n{entry}\ndeploy.log\ndeploy_history.json\n")
            self.logger.info(".gitignore を作成し、設定ファイルを追加しました")
    
    def run_setup(self, test_connection: bool = True):
        """セットアップを実行"""
        # 既存の設定ファイルがある場合の確認
        if os.path.exists(self.config_file):
            overwrite = input(f"既存の設定ファイル '{self.config_file}' が存在します。上書きしますか？ [y/N]: ").strip().lower()
            if overwrite not in ['y', 'yes']:
                self.logger.info("セットアップを中止しました")
                return False
        
        # 対話型設定作成
        config = self.create_config_interactive()
        if not config:
            return False
        
        # FTP接続テスト
        if test_connection:
            if not self.test_ftp_connection(config):
                self.logger.error("FTP接続テストに失敗しました。設定を確認してください。")
                return False
        
        # ローカルパス確認
        path_valid = self.validate_local_paths(config)
        if not path_valid:
            self.logger.warning("一部のローカルパスに問題があります。後で確認してください。")
        
        # .gitignore への追加
        try:
            self.create_gitignore_entry()
        except Exception as e:
            self.logger.warning(f".gitignore の更新に失敗: {e}")
        
        # セットアップ完了
        print("\n=== セットアップ完了 ===")
        self.logger.info("セットアップが正常に完了しました")
        self.logger.info("次のコマンドでデプロイできます:")
        
        for app in config['apps']:
            print(f"  python deploy.py --app {app['name']}")
        
        return True

def main():
    parser = argparse.ArgumentParser(description='ロリポップデプロイツール - セットアップ')
    parser.add_argument('--config', '-c', default='deploy_config.json', help='設定ファイルのパス')
    parser.add_argument('--no-test', action='store_true', help='FTP接続テストをスキップ')
    
    args = parser.parse_args()
    
    # セットアップツールを初期化
    setup_tool = DeploySetup(args.config)
    
    # セットアップを実行
    success = setup_tool.run_setup(not args.no_test)
    
    if success:
        print("\nセットアップが正常に完了しました！")
        sys.exit(0)
    else:
        print("\nセットアップでエラーが発生しました")
        sys.exit(1)

if __name__ == '__main__':
    main()