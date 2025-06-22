# ロリポップサーバー向けデプロイツール

Git の差分を基に FTP でファイルをアップロードするデプロイツールです。

## 機能

- Git の差分を基にした効率的なデプロイ
- 複数アプリの設定管理
- 前回デプロイからの変更ファイルのみアップロード
- ファイル除外パターンの設定
- デプロイログの管理
- 対話型セットアップ
- ドライランモード (`--dry-run`) でデプロイ内容を事前に確認
- FTP接続テスト機能

## セットアップ

### 1. 必要なライブラリのインストール

```bash
# テストを行う場合は pytest と pytest-mock をインストールしてください
pip install pytest pytest-mock
```

### 2. 初期セットアップ

```bash
# セットアップを実行（対話型で設定を入力）
python init.py
```

セットアップでは以下を行います：
- FTP接続情報の設定（ホスト、ユーザー名、パスワード）
- アプリケーション設定（名前、ローカルパス、リモートパス）
- FTP接続テスト
- ローカルパス・Gitリポジトリの確認
- .gitignore への設定ファイル追加

### 3. セットアップオプション

```bash
# FTP接続テストをスキップしてセットアップ
python init.py --no-test

# カスタム設定ファイル名でセットアップ
python init.py --config custom_config.json
```

## 使用方法

### デプロイコマンド

```bash
# 指定したアプリをデプロイ
python deploy.py --app my-app

# 短縮形
python deploy.py -a my-app
```

### 強制デプロイ（全ファイル）

```bash
# 前回のデプロイ情報を無視して全ファイルをアップロード
python deploy.py --app my-app --all

# 短縮形
python deploy.py -a my-app -A
```

### ドライラン（事前確認） 

--dry-run オプションを付けると、実際にファイルのアップロードや削除を行わずに、どのファイルが処理対象になるかを確認できます。 

```bash 
# デプロイ内容を事前に確認 
python deploy.py --app my-app --dry-run 
# 短縮形 
python deploy.py -a my-app -d
```
これにより、意図しないファイルがデプロイされるのを防ぐことができます。

### アプリ一覧表示

```bash
# 設定されているアプリの一覧を表示
python deploy.py --list

# 短縮形
python deploy.py -l
```

### カスタム設定ファイル使用

```bash
# 別の設定ファイルを使用
python deploy.py --app my-app --config custom_config.json

# 短縮形
python deploy.py -a my-app -c custom_config.json
```

## 設定項目詳細

### FTP設定

```json
"ftp": {
  "host": "ftp.lolipop.jp",
  "username": "your-username",
  "password": "your-password"
}
```

### アプリ設定

```json
"apps": [
  {
    "name": "my-app",
    "local_path": "C:\\xampp\\htdocs\\my-app",
    "remote_path": "/my-app",
    "always_deploy_files": [ ".env", "dist" ]
  }
]
```

### 常にデプロイするファイル (always_deploy_files) 

always_deploy_files は、各アプリごとに設定できるオプションです。 
ここに指定されたファイルやフォルダは、Gitの差分に関わらず、常にデプロイ対象となります。

- 用途:

.gitignore に登録されているが、サーバーにはアップロードしたいファイル（例: .env）。
ビルドプロセスによって生成され、Git管理下にないフォルダ（例: dist, build）。 

- 指定方法:

アプリの local_path からの相対パスで指定します。
フォルダを指定した場合、そのフォルダ内のすべてのファイルが再帰的に対象となります

### 除外パターン

アップロード対象から除外するファイル・ディレクトリのパターン：

```json
"exclude_patterns": [
  ".git", 
  ".gitignore",
  "*.pyc", 
  ".env"
]
```

### その他の設定

```json
"overwrite": true,
"timeout": 30
```

## ワークフロー

1. ローカルでコード修正
2. Git でコミット
3. デプロイツールを実行
4. 前回デプロイからの差分ファイルのみアップロード

## ログファイル

- `deploy.log`: デプロイ実行ログ
- `deploy_history.json`: 各アプリの最終デプロイ情報

## トラブルシューティング

### FTP接続エラー

- ユーザー名・パスワードを確認
- ホスト名が正しいか確認
- ファイアウォールの設定を確認

### Git関連エラー

- プロジェクトディレクトリがGitリポジトリか確認
- Gitがインストールされているか確認

### ファイルアップロードエラー

- リモートディレクトリの権限を確認
- ファイルサイズ制限を確認
- ネットワーク接続を確認

## セキュリティ注意事項

- `deploy_config.json` にはパスワードが含まれるため、Gitリポジトリには含めないでください
- `.gitignore` に `deploy_config.json` を追加することを推奨します

## 例：初回セットアップから実行まで

```bash
# 1. ツールファイルを配置
# init.py と deploy.py をプロジェクトルートに配置

# 2. セットアップ実行（対話型）
python init.py
# FTP情報とアプリ設定を入力
# 接続テストとパス確認を自動実行

# 3. デプロイ実行
python deploy.py --app my-app
# 初回は全ファイルがアップロード

# 4. コード修正後の2回目以降
# Git でコミット後
python deploy.py --app my-app
# 差分ファイルのみアップロード
```

## ファイル構成

```
project/
├── init.py              # セットアップツール
├── deploy.py            # デプロイ実行ツール
├── deploy_config.json   # 設定ファイル（セットアップ時に作成）
├── deploy.log           # デプロイ実行ログ
├── deploy_history.json  # デプロイ履歴データ
├── .gitignore           # Git除外設定（自動更新）
├── pytest.ini           # pytest設定ファイル
└── tests/               # テストディレクトリ
```

## テストの実行方法

このプロジェクトでは [`pytest`](https://docs.pytest.org/) を使用してユニットテストを記述しています。テストコードは `./tests` ディレクトリに配置されています。

### テストの実行

```bash
# 必要なライブラリをインストール
pip install pytest pytest-mock

# すべてのテストを実行
pytest
```


## ライセンス (License)

**ロリポップサーバー向けデプロイツール** は [MIT license](https://opensource.org/licenses/MIT) のもとでオープンソースソフトウェアとして提供されています。

**Lolipop Deploy Tool** is an open-source software licensed under the [MIT license](https://opensource.org/licenses/MIT).