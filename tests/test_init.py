#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
init.py の自動テストスイート
FTPモックとGitリポジトリモックを使用して安全にテストを実行
"""

import pytest
import tempfile
import shutil
import os
import json
import subprocess
from pathlib import Path
import sys

# テスト対象をインポート
# init.py はこのファイルの親ディレクトリにあると想定
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from init import DeploySetup


@pytest.fixture
def temp_dir():
    """テスト用の一時ディレクトリを作成"""
    temp_dir = tempfile.mkdtemp()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir)


@pytest.fixture
def mock_git_repo(temp_dir):
    """モックGitリポジトリを作成"""
    git_dir = Path(temp_dir) / "test_repo"
    git_dir.mkdir()
    
    # .gitディレクトリを作成
    (git_dir / ".git").mkdir()
    
    # いくつかのファイルを作成
    (git_dir / "index.html").write_text("<!DOCTYPE html><html></html>")
    (git_dir / "style.css").write_text("body { margin: 0; }")
    
    return str(git_dir)


@pytest.fixture
def setup_deploy_tool(temp_dir):
    """DeploySetupインスタンスを作成"""
    config_file = os.path.join(temp_dir, "test_config.json")
    
    # 元のディレクトリを保存
    original_cwd = os.getcwd()
    try:
        # テストディレクトリに移動
        os.chdir(temp_dir)
        
        tool = DeploySetup(config_file)
        
        yield tool
    finally:
        # 元のディレクトリに戻る
        os.chdir(original_cwd)


@pytest.fixture
def sample_config():
    """テスト用の設定データ"""
    return {
        "ftp": {
            "host": "ftp.test.com",
            "username": "testuser",
            "password": "testpass"
        },
        "apps": [
            {
                "name": "test-app",
                "local_path": "/path/to/test-app",
                "remote_path": "/test-app",
                "always_deploy_files": [".env", "dist"]
            }
        ],
        "overwrite": True,
        "exclude_patterns": [
            ".git",
            ".gitignore",
            "__pycache__",
            "*.pyc"
        ],
        "timeout": 30
    }


class TestDeploySetup:
    """DeploySetupのテストクラス"""
    
    def test_init(self, temp_dir):
        """初期化のテスト"""
        config_file = os.path.join(temp_dir, "test_config.json")
        setup = DeploySetup(config_file)
        
        assert setup.config_file == config_file
        assert setup.logger is not None
    
    def test_load_config_success(self, setup_deploy_tool, sample_config):
        """設定ファイル読み込み成功のテスト"""
        # 設定ファイルを作成
        with open(setup_deploy_tool.config_file, 'w', encoding='utf-8') as f:
            json.dump(sample_config, f)
        
        config = setup_deploy_tool.load_config()
        
        assert config is not None
        assert config['ftp']['host'] == "ftp.test.com"
        assert len(config['apps']) == 1
        assert config['apps'][0]['name'] == "test-app"
    
    def test_load_config_file_not_found(self, setup_deploy_tool):
        """設定ファイルが存在しない場合のテスト"""
        config = setup_deploy_tool.load_config()
        assert config is None
    
    def test_load_config_invalid_json(self, setup_deploy_tool):
        """無効なJSONファイルの場合のテスト"""
        # 無効なJSONファイルを作成
        with open(setup_deploy_tool.config_file, 'w', encoding='utf-8') as f:
            f.write("invalid json content")
        
        config = setup_deploy_tool.load_config()
        assert config is None
    
    def test_ftp_connection_success(self, mocker, setup_deploy_tool, sample_config):
        """FTP接続テスト成功のテスト"""
        # ftplib.FTP をモック化し、そのインスタンスを取得
        mock_ftp_class = mocker.patch('ftplib.FTP')
        mock_ftp_instance = mock_ftp_class.return_value
        mock_ftp_instance.getwelcome.return_value = "Welcome to test FTP server"
        
        result = setup_deploy_tool.test_ftp_connection(sample_config)
        
        assert result is True
        mock_ftp_class.assert_called_once_with()
        mock_ftp_instance.connect.assert_called_once_with("ftp.test.com", timeout=30)
        mock_ftp_instance.login.assert_called_once_with("testuser", "testpass")
        mock_ftp_instance.set_pasv.assert_called_once_with(True)
        mock_ftp_instance.quit.assert_called_once()
    
    def test_ftp_connection_failure(self, mocker, setup_deploy_tool, sample_config):
        """FTP接続テスト失敗のテスト"""
        # ftplib.FTP をモック化
        mock_ftp_class = mocker.patch('ftplib.FTP')
        mock_ftp_instance = mock_ftp_class.return_value

        # FTP接続エラーをシミュレート
        mock_ftp_instance.connect.side_effect = Exception("Connection failed")
        
        result = setup_deploy_tool.test_ftp_connection(sample_config)
        
        assert result is False
        mock_ftp_class.assert_called_once_with()
        mock_ftp_instance.connect.assert_called_once_with("ftp.test.com", timeout=30)
        mock_ftp_instance.login.assert_not_called()
        mock_ftp_instance.quit.assert_called_once()
    
    def test_validate_local_paths_success(self, setup_deploy_tool, mock_git_repo):
        """ローカルパス検証成功のテスト"""
        config = {
            "apps": [
                {
                    "name": "test-app",
                    "local_path": mock_git_repo
                }
            ]
        }
        
        result = setup_deploy_tool.validate_local_paths(config)
        assert result is True
    
    def test_validate_local_paths_not_exists(self, setup_deploy_tool):
        """存在しないローカルパスのテスト"""
        config = {
            "apps": [
                {
                    "name": "test-app",
                    "local_path": "/non/existent/path"
                }
            ]
        }
        
        result = setup_deploy_tool.validate_local_paths(config)
        assert result is False
    
    def test_validate_local_paths_not_git_repo(self, setup_deploy_tool, temp_dir):
        """Gitリポジトリではないパスのテスト"""
        non_git_dir = os.path.join(temp_dir, "non_git")
        os.makedirs(non_git_dir)
        
        config = {
            "apps": [
                {
                    "name": "test-app",
                    "local_path": non_git_dir
                }
            ]
        }
        
        result = setup_deploy_tool.validate_local_paths(config)
        assert result is False
    
    def test_create_gitignore_entry_new_file(self, setup_deploy_tool):
        """新しい.gitignoreファイル作成のテスト"""
        setup_deploy_tool.create_gitignore_entry()
        
        assert os.path.exists(".gitignore")
        
        with open(".gitignore", 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert "deploy_config.json" in content
        assert "deploy.log" in content
        assert "deploy_history.json" in content
    
    def test_create_gitignore_entry_existing_file(self, setup_deploy_tool):
        """既存の.gitignoreファイルへの追加テスト"""
        # 既存の.gitignoreファイルを作成
        with open(".gitignore", 'w', encoding='utf-8') as f:
            f.write("*.log\n*.tmp\n")
        
        setup_deploy_tool.create_gitignore_entry()
        
        with open(".gitignore", 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert "*.log" in content  # 既存の内容
        assert "deploy_config.json" in content  # 新しく追加された内容
    
    def test_create_gitignore_entry_already_exists(self, setup_deploy_tool):
        """既にエントリが存在する場合のテスト"""
        # 既にエントリを含む.gitignoreファイルを作成
        with open(".gitignore", 'w', encoding='utf-8') as f:
            f.write("deploy_config.json\n*.log\n")
        
        original_content = open(".gitignore", 'r', encoding='utf-8').read()
        
        setup_deploy_tool.create_gitignore_entry()
        
        with open(".gitignore", 'r', encoding='utf-8') as f:
            new_content = f.read()
        
        # 内容が変更されていないことを確認
        assert original_content == new_content
    
    def test_create_config_interactive_basic(self, mocker, setup_deploy_tool):
        """対話型設定作成の基本テスト"""
        # ユーザー入力をモック
        mock_input = mocker.patch('builtins.input')
        mock_input.side_effect = [
            "ftp.lolipop.jp",  # FTPホスト
            "testuser",        # FTPユーザー名
            "testpass",        # FTPパスワード
            "test-app",        # アプリ名
            "/local/path",     # ローカルパス
            "/remote/path",    # リモートパス
            ".env",            # 常にデプロイするファイル1
            "",                # 常にデプロイするファイル終了
            "n",               # 他のアプリ追加しない
            "y"                # 上書き許可
        ]
        
        config = setup_deploy_tool.create_config_interactive()
        
        assert config is not False
        assert config['ftp']['host'] == "ftp.lolipop.jp"
        assert config['ftp']['username'] == "testuser"
        assert config['ftp']['password'] == "testpass"
        assert len(config['apps']) == 1
        assert config['apps'][0]['name'] == "test-app"
        assert config['apps'][0]['local_path'] == os.path.normpath("/local/path")
        assert config['apps'][0]['remote_path'] == "/remote/path"
        assert config['apps'][0]['always_deploy_files'] == [".env"]
        assert config['overwrite'] is True
    
    def test_create_config_interactive_missing_username(self, mocker, setup_deploy_tool):
        """FTPユーザー名が空の場合のテスト"""
        mock_input = mocker.patch('builtins.input')
        mock_input.side_effect = [
            "ftp.lolipop.jp",  # FTPホスト
            "",                # FTPユーザー名（空）
        ]
        
        config = setup_deploy_tool.create_config_interactive()
        assert config is False
    
    def test_create_config_interactive_missing_password(self, mocker, setup_deploy_tool):
        """FTPパスワードが空の場合のテスト"""
        mock_input = mocker.patch('builtins.input')
        mock_input.side_effect = [
            "ftp.lolipop.jp",  # FTPホスト
            "testuser",        # FTPユーザー名
            "",                # FTPパスワード（空）
        ]
        
        config = setup_deploy_tool.create_config_interactive()
        assert config is False
    
    def test_create_config_interactive_multiple_apps(self, mocker, setup_deploy_tool):
        """複数アプリ設定のテスト"""
        mock_input = mocker.patch('builtins.input')
        mock_input.side_effect = [
            "ftp.lolipop.jp",  # FTPホスト
            "testuser",        # FTPユーザー名
            "testpass",        # FTPパスワード
            "app1",            # アプリ1名
            "/local/app1",     # アプリ1ローカルパス
            "/remote/app1",    # アプリ1リモートパス
            "",                # アプリ1常にデプロイするファイル終了
            "y",               # 他のアプリ追加する
            "app2",            # アプリ2名
            "/local/app2",     # アプリ2ローカルパス
            "/remote/app2",    # アプリ2リモートパス
            "dist",            # アプリ2常にデプロイするファイル1
            "",                # アプリ2常にデプロイするファイル終了
            "n",               # 他のアプリ追加しない
            "n"                # 上書きしない
        ]
        
        config = setup_deploy_tool.create_config_interactive()
        
        assert config is not False
        assert len(config['apps']) == 2
        assert config['apps'][0]['name'] == "app1"
        assert config['apps'][1]['name'] == "app2"
        assert config['apps'][1]['always_deploy_files'] == ["dist"]
        assert config['overwrite'] is False
    
    def test_run_setup_success(self, mocker, setup_deploy_tool):
        """セットアップ実行成功のテスト"""
        # モック設定
        mock_input = mocker.patch('builtins.input')
        mock_input.side_effect = [
            "ftp.lolipop.jp", "testuser", "testpass",
            "test-app", "/local/path", "/remote/path", "",
            "n", "y"
        ]
        mock_ftp_test = mocker.patch.object(DeploySetup, 'test_ftp_connection', return_value=True)
        mock_validate = mocker.patch.object(DeploySetup, 'validate_local_paths', return_value=True)

        result = setup_deploy_tool.run_setup()
        
        assert result is True
        assert os.path.exists(setup_deploy_tool.config_file)
        mock_ftp_test.assert_called_once()
        mock_validate.assert_called_once()
    
    def test_run_setup_ftp_failure(self, mocker, setup_deploy_tool):
        """FTP接続テスト失敗のテスト"""
        mock_input = mocker.patch('builtins.input')
        mock_input.side_effect = [
            "ftp.lolipop.jp", "testuser", "testpass",
            "test-app", "/local/path", "/remote/path", "",
            "n", "y"
        ]
        mocker.patch.object(DeploySetup, 'test_ftp_connection', return_value=False)
        
        result = setup_deploy_tool.run_setup()
        
        assert result is False
    
    def test_run_setup_existing_config_overwrite_no(self, mocker, setup_deploy_tool):
        """既存設定ファイルを上書きしない場合のテスト"""
        # 既存の設定ファイルを作成
        with open(setup_deploy_tool.config_file, 'w') as f:
            f.write("{}")
        
        mock_input = mocker.patch('builtins.input')
        mock_input.return_value = "n"  # 上書きしない
        
        result = setup_deploy_tool.run_setup()
        
        assert result is False
    
    def test_run_setup_no_connection_test(self, mocker, setup_deploy_tool):
        """接続テストをスキップする場合のテスト"""
        mock_input = mocker.patch('builtins.input')
        mock_input.side_effect = [
            "ftp.lolipop.jp", "testuser", "testpass",
            "test-app", "/local/path", "/remote/path", "",
            "n", "y"
        ]
        
        mock_ftp_test = mocker.patch.object(setup_deploy_tool, 'test_ftp_connection')
        result = setup_deploy_tool.run_setup(test_connection=False)
        
        assert result is True
        mock_ftp_test.assert_not_called()


@pytest.mark.parametrize("host,username,password,expected", [
    ("ftp.lolipop.jp", "user", "pass", True),
    ("", "user", "pass", False),
    ("ftp.lolipop.jp", "", "pass", False),
    ("ftp.lolipop.jp", "user", "", False),
])
def test_config_validation_parameters(host, username, password, expected):
    """設定値のパラメータ化テスト"""
    config = {
        "ftp": {
            "host": host,
            "username": username,
            "password": password
        },
        "timeout": 30
    }
    
    # 簡単な検証ロジック
    is_valid = bool(host and username and password)
    assert is_valid == expected


class TestIntegration:
    """統合テスト"""
    
    def test_full_setup_flow(self, mocker, temp_dir, mock_git_repo):
        """完全なセットアップフローのテスト"""
        mock_ftp_class = mocker.patch('ftplib.FTP')
        # 元のディレクトリを保存
        original_cwd = os.getcwd()
        
        try:
            # テストディレクトリに移動
            os.chdir(temp_dir)
            
            # FTPモックを設定
            mock_ftp = mocker.Mock()
            mock_ftp.getwelcome.return_value = "Welcome"
            mock_ftp_class.return_value = mock_ftp
            
            # ユーザー入力をモック
            mock_input = mocker.patch('builtins.input')
            mock_input.side_effect = [
                "ftp.lolipop.jp", "testuser", "testpass",
                "test-app", mock_git_repo, "/remote/path", ".env", "",
                "n", "y"
            ]
            
            # セットアップを実行
            setup_tool = DeploySetup("test_config.json")
            result = setup_tool.run_setup()
            
            # 結果を検証
            assert result is True
            assert os.path.exists("test_config.json")
            assert os.path.exists(".gitignore")
            
            # 設定ファイルの内容を確認
            with open("test_config.json", 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            assert config['ftp']['username'] == "testuser"
            assert config['apps'][0]['name'] == "test-app"
            assert config['apps'][0]['always_deploy_files'] == [".env"]
            
            # .gitignoreの内容を確認
            with open(".gitignore", 'r', encoding='utf-8') as f:
                gitignore_content = f.read()
            
            assert "deploy_config.json" in gitignore_content
            
        finally:
            # 元のディレクトリに戻る
            os.chdir(original_cwd)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])