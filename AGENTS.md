# Codex エージェント向けガイドライン

このリポジトリでは以下の方針で自動化タスクを実行してください。

## テスト実行
- 依存パッケージを `requirements.txt` からインストール後、`pytest -q` を実行してテストしてください。

## コードスタイル
- Python コードは基本的に PEP8 に従います。特別なフォーマッタ設定はありません。

## 環境構築
1. `python3 -m venv venv`
2. `source venv/bin/activate`
3. `pip install -r requirements.txt`

`.env.example` をコピーして `.env` を作成し、必要に応じて値を変更します。`.env` は Git 管理対象外です。

## PR 作成時
- コミットメッセージは日本語で簡潔に記述してください。
- PR では変更内容の要約とテスト結果を明記してください。


