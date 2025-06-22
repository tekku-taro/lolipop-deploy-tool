#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deploy.py の自動テストスイート
FTPモックとGitリポジトリモックを使用して安全にテストを実行
"""

import pytest
import tempfile
import shutil
import os
import json
import subprocess
from pathlib import Path
from unittest.mock import call # Keep call for potential assert_has_calls
import sys

# テスト対象をインポート
# deploy.py はこのファイルの親ディレクトリにあると想定
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from deploy import LolipopDeployTool

@pytest.fixture
def setup_deploy_tool():
    """
    テストに必要な一時ディレクトリ、設定ファイル、Gitリポジトリを作成し、
    LolipopDeployToolのインスタンスを初期化して提供するpytestフィクスチャ。
    テスト終了後にクリーンアップを行う。
    """
    original_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    
    try:
        os.chdir(temp_dir)
        
        # テスト用の設定データ
        config_data = {
            "ftp": {
                "host": "test.server.com",
                "username": "testuser",
                "password": "testpass"
            },
            "apps": [
                {
                    "name": "testapp",
                    "local_path": str(Path(temp_dir) / "testapp"),
                    "remote_path": "/public_html/testapp",
                    "always_deploy_files": ["config/", "assets/important.js"]
                }
            ],
            "exclude_patterns": ["*.log", ".git"],
            "timeout": 30,
            "overwrite": True
        }
        
        # 設定ファイルを作成
        config_file = "test_config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        # テスト用アプリディレクトリとGitリポジリを作成
        app_path = Path(temp_dir) / "testapp"
        app_path.mkdir(exist_ok=True)
        
        # Gitリポジリを初期化
        subprocess.run(['git', 'init'], cwd=app_path, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=app_path, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=app_path, check=True)
        
        # 初期ファイルを作成
        (app_path / "index.html").write_text("<html><body>Hello World</body></html>", encoding='utf-8')
        (app_path / "style.css").write_text("body { color: blue; }", encoding='utf-8')
        
        # ディレクトリも作成
        config_dir = app_path / "config"
        config_dir.mkdir()
        (config_dir / "settings.json").write_text('{"debug": true}', encoding='utf-8')
        
        assets_dir = app_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "important.js").write_text("console.log('important');", encoding='utf-8')
        (assets_dir / "other.js").write_text("console.log('other');", encoding='utf-8')
        
        # 除外ファイルも作成
        (app_path / "debug.log").write_text("debug info", encoding='utf-8')
        
        # 初回コミット
        subprocess.run(['git', 'add', '.'], cwd=app_path, check=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=app_path, check=True)
        
        # デプロイツールを初期化
        deploy_tool = LolipopDeployTool(config_file)
        
        # テスト関数に提供する値
        yield deploy_tool, temp_dir, config_file, config_data, app_path
        
    finally:
        # クリーンアップ
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir, ignore_errors=True)

class TestLolipopDeployTool:
    """LolipopDeployToolのテストクラス"""
    
    def test_load_config(self, setup_deploy_tool):
        """設定ファイル読み込みのテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        assert deploy_tool.config['ftp']['host'] == 'test.server.com'
        assert len(deploy_tool.config['apps']) == 1
        assert deploy_tool.config['apps'][0]['name'] == 'testapp'
    
    def test_load_config_file_not_found(self):
        """存在しない設定ファイルを指定した場合のテスト"""
        with pytest.raises(SystemExit):
            LolipopDeployTool("nonexistent_config.json")
    
    def test_get_app_config(self, setup_deploy_tool):
        """アプリ設定取得のテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        app_config = deploy_tool.get_app_config("testapp")
        assert app_config is not None
        assert app_config['name'] == 'testapp'
        
        app_config = deploy_tool.get_app_config("nonexistent")
        assert app_config is None
    
    def test_get_current_commit(self, setup_deploy_tool):
        """現在のコミットハッシュ取得のテスト"""
        deploy_tool, _, _, _, app_path = setup_deploy_tool
        commit_hash = deploy_tool.get_current_commit(str(app_path))
        assert isinstance(commit_hash, str)
        assert len(commit_hash) == 40  # SHA-1ハッシュは40文字
    
    def test_filter_files(self, setup_deploy_tool):
        """ファイルフィルタリングのテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        test_files = [
            "index.html",
            "style.css",
            "debug.log",
            ".git/config",
            "src/main.js"
        ]
        
        filtered = deploy_tool.filter_files(test_files)
        
        # 除外されるべきファイル
        assert "debug.log" not in filtered
        assert ".git/config" not in filtered
        
        # 残るべきファイル
        assert "index.html" in filtered
        assert "style.css" in filtered
        assert "src/main.js" in filtered
    
    def test_get_changed_files_initial(self, setup_deploy_tool):
        """初回デプロイ時の変更ファイル取得テスト"""
        deploy_tool, _, _, _, app_path = setup_deploy_tool
        changes = deploy_tool.get_changed_files(str(app_path), None)
        
        assert "upload" in changes
        assert "delete" in changes
        assert len(changes["delete"]) == 0  # 初回は削除ファイルなし
        
        # アップロードファイルに期待するファイルが含まれているか
        upload_files = changes["upload"]
        assert "index.html" in upload_files
        assert "style.css" in upload_files
        assert "config/settings.json" in upload_files
        
        # 除外ファイルが含まれていないか
        assert "debug.log" not in upload_files
    
    def test_get_changed_files_with_changes(self, setup_deploy_tool):
        """変更ありの場合の差分ファイル取得テスト"""
        deploy_tool, _, _, _, app_path = setup_deploy_tool
        
        # 初回コミットのハッシュを取得
        initial_commit = deploy_tool.get_current_commit(str(app_path))
        
        # ファイルを変更してコミット
        (app_path / "index.html").write_text("<html><body>Updated</body></html>", encoding='utf-8')
        (app_path / "new_file.txt").write_text("New content", encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=app_path, check=True)
        subprocess.run(['git', 'commit', '-m', 'Update files'], cwd=app_path, check=True)
        
        # ファイルを削除してコミット
        (app_path / "style.css").unlink()
        subprocess.run(['git', 'add', '-A'], cwd=app_path, check=True)
        subprocess.run(['git', 'commit', '-m', 'Delete style.css'], cwd=app_path, check=True)
        
        # 差分を取得
        changes = deploy_tool.get_changed_files(str(app_path), initial_commit)
        
        # 変更・追加されたファイル
        assert "index.html" in changes["upload"]
        assert "new_file.txt" in changes["upload"]
        
        # 削除されたファイル
        assert "style.css" in changes["delete"]
    
    def test_deploy_log_operations(self, setup_deploy_tool):
        """デプロイログの操作テスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        app_name = "testapp"
        commit_hash = "abc123def456"
        
        # 初期状態では前回デプロイコミットはNone
        last_commit = deploy_tool.get_last_deploy_commit(app_name)
        assert last_commit is None
        
        # デプロイコミットを保存
        deploy_tool.save_deploy_commit(app_name, commit_hash)
        
        # 保存されたコミットハッシュを取得
        last_commit = deploy_tool.get_last_deploy_commit(app_name)
        assert last_commit == commit_hash
        
        # ファイルが実際に作成されているか確認
        assert os.path.exists(deploy_tool.deploy_log_file)
    
    def test_connect_ftp(self, setup_deploy_tool, mocker):
        """FTP接続のテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        
        mock_ftp_class = mocker.patch('deploy.ftplib.FTP')
        mock_ftp = mock_ftp_class.return_value
        
        ftp = deploy_tool.connect_ftp()
        
        # FTPインスタンスが作成されたか
        mock_ftp_class.assert_called_once()
        # 適切なメソッドが呼ばれたか
        mock_ftp.connect.assert_called_once_with('test.server.com', timeout=30)
        mock_ftp.login.assert_called_once_with('testuser', 'testpass')
        mock_ftp.set_pasv.assert_called_once_with(True)
        
        assert ftp == mock_ftp
    
    def test_upload_file(self, setup_deploy_tool, mocker):
        """ファイルアップロードのテスト"""
        deploy_tool, temp_dir, _, _, _ = setup_deploy_tool
        mock_ftp = mocker.Mock()
        
        # テストファイルを作成
        test_file = Path(temp_dir) / "test_upload.txt"
        test_file.write_text("test content", encoding='utf-8')
        
        # アップロードテスト
        result = deploy_tool.upload_file(mock_ftp, test_file, "/remote/test_upload.txt")
        
        assert result is True
        mock_ftp.storbinary.assert_called_once()
    
    def test_delete_remote_file(self, setup_deploy_tool, mocker):
        """リモートファイル削除のテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        mock_ftp = mocker.Mock()
        
        # 削除成功のテスト
        result = deploy_tool.delete_remote_file(mock_ftp, "/remote/test.txt")
        
        assert result is True
        mock_ftp.delete.assert_called_once_with("/remote/test.txt")
    
    def test_ensure_remote_directory(self, setup_deploy_tool, mocker):
        """リモートディレクトリ作成のテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        mock_ftp = mocker.Mock()
        
        # ディレクトリが存在しない場合（error_permが発生）
        from ftplib import error_perm
        mock_ftp.cwd.side_effect = error_perm("550 Directory not found")
        
        deploy_tool.ensure_remote_directory(mock_ftp, "/remote/new/directory")
        
        # mkdメソッドが呼ばれたか確認
        assert mock_ftp.mkd.called
    
    def test_deploy_dry_run(self, setup_deploy_tool, mocker):
        """ドライランモードのテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        app_name = "testapp"
        
        # ドライランでデプロイ実行
        mock_connect_ftp = mocker.patch('deploy.LolipopDeployTool.connect_ftp')
        result = deploy_tool.deploy(app_name, dry_run=True)
        
        # 成功するはず
        assert result is True
        
        # FTP接続は行われないはず
        mock_connect_ftp.assert_not_called()
    
    def test_deploy_no_changes(self, setup_deploy_tool, mocker):
        """変更がない場合のデプロイテスト"""
        deploy_tool, _, _, _, app_path = setup_deploy_tool
        app_name = "testapp"
        
        # このテストでは always_deploy_files を無効にして、純粋な「Gitの変更なし」をテストする
        deploy_tool.config['apps'][0]['always_deploy_files'] = []
        
        # 現在のコミットを前回デプロイとして保存
        current_commit = deploy_tool.get_current_commit(str(app_path))
        deploy_tool.save_deploy_commit(app_name, current_commit)
        
        # デプロイ実行（変更なし）
        mock_connect_ftp = mocker.patch('deploy.LolipopDeployTool.connect_ftp')
        result = deploy_tool.deploy(app_name)
        
        # 成功するはず
        assert result is True
        
        # FTP接続は行われないはず（変更がなく、always_deploy_filesもないため）
        mock_connect_ftp.assert_not_called()
    
    def test_deploy_with_changes(self, setup_deploy_tool, mocker):
        """変更がある場合のデプロイテスト"""
        deploy_tool, _, _, _, app_path = setup_deploy_tool
        app_name = "testapp"
        
        # 現在のコミットを前回デプロイとして保存
        current_commit = deploy_tool.get_current_commit(str(app_path))
        deploy_tool.save_deploy_commit(app_name, current_commit)
        
        # ファイルを変更してコミット
        (app_path / "index.html").write_text("<html><body>Changed</body></html>", encoding='utf-8')
        subprocess.run(['git', 'add', '.'], cwd=app_path, check=True)
        subprocess.run(['git', 'commit', '-m', 'Change file'], cwd=app_path, check=True)
        
        # モックFTPを設定
        mock_ftp = mocker.Mock()
        mock_ftp.nlst.return_value = []  # clear_remote_directory内のイテレーション用
        mock_connect_ftp = mocker.patch('deploy.LolipopDeployTool.connect_ftp', return_value=mock_ftp)
        
        # デプロイ実行
        result = deploy_tool.deploy(app_name)
        
        # 成功するはず
        assert result is True
        
        # FTP接続が行われたはず
        mock_connect_ftp.assert_called_once()
        
        # アップロードが実行されたはず
        mock_ftp.storbinary.assert_called()
    
    def test_deploy_always_deploy_files(self, setup_deploy_tool, mocker):
        """always_deploy_files機能のテスト"""
        deploy_tool, _, _, _, app_path = setup_deploy_tool
        app_name = "testapp"
        
        # 現在のコミットを前回デプロイとして保存（変更なしの状態を作る）
        current_commit = deploy_tool.get_current_commit(str(app_path))
        deploy_tool.save_deploy_commit(app_name, current_commit)
        
        # モックFTPを設定
        mock_ftp = mocker.Mock()
        mock_ftp.nlst.return_value = []  # clear_remote_directory内のイテレーション用
        mock_connect_ftp = mocker.patch('deploy.LolipopDeployTool.connect_ftp', return_value=mock_ftp)
        
        # デプロイ実行（always_deploy_filesが設定されているので実行されるはず）
        result = deploy_tool.deploy(app_name)
        
        # 成功するはず
        assert result is True
        
        # FTP接続が行われたはず（always_deploy_filesがあるため）
        mock_connect_ftp.assert_called_once()
    
    def test_deploy_invalid_app(self, setup_deploy_tool):
        """存在しないアプリ名を指定した場合のテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        result = deploy_tool.deploy("nonexistent_app")
        assert result is False
    
    def test_deploy_invalid_local_path(self, setup_deploy_tool):
        """存在しないローカルパスの場合のテスト"""
        deploy_tool, _, _, _, _ = setup_deploy_tool
        # 設定を変更
        deploy_tool.config['apps'][0]['local_path'] = "/nonexistent/path"
        
        result = deploy_tool.deploy("testapp")
        assert result is False
    
    def test_deploy_non_git_repository(self, setup_deploy_tool):
        """Gitリポジトリではないディレクトリの場合のテスト"""
        deploy_tool, temp_dir, _, _, _ = setup_deploy_tool
        # 非Gitディレクトリを作成
        non_git_path = Path(temp_dir) / "non_git_app"
        non_git_path.mkdir()
        (non_git_path / "file.txt").write_text("content", encoding='utf-8')
        
        # 設定を変更
        deploy_tool.config['apps'][0]['local_path'] = str(non_git_path)
        
        result = deploy_tool.deploy("testapp")
        assert result is False

class TestCommandLineInterface:
    """コマンドライン機能のテストクラス"""
    
    @pytest.fixture
    def cli_setup(self):
        """CLIテスト用の設定ファイルと一時ディレクトリをセットアップ"""
        temp_dir = tempfile.mkdtemp()
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            
            # テスト用設定ファイル作成
            config_data = {
                "apps": [
                    {"name": "app1", "local_path": "/path1", "remote_path": "/remote1"},
                    {"name": "app2", "local_path": "/path2", "remote_path": "/remote2"}
                ],
                "ftp": {"host": "test.com", "username": "user", "password": "pass"}
            }
            
            config_file = "test_config.json"
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f)
            
            yield config_file
        finally:
            # クリーンアップ
            os.chdir(original_cwd)
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    def test_list_apps(self, cli_setup, capsys):
        """アプリ一覧表示のテスト"""
        config_file = cli_setup
        deploy_tool = LolipopDeployTool(config_file)
        
        # 標準出力をキャプチャ
        deploy_tool.list_apps()
        
        captured = capsys.readouterr()
        assert "app1" in captured.out
        assert "app2" in captured.out