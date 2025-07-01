# 勤怠管理システム モジュール分割移行ガイド

## 概要
monolithicなapp.py（1436行）を機能別モジュールに分割しました。

## 変更点

### 1. ディレクトリ構造
```
kintai-system/
├── app/
│   ├── __init__.py          # Flaskアプリケーションファクトリ
│   ├── auth/                # 認証・認可機能
│   │   └── __init__.py
│   ├── attendance/          # 勤怠管理機能
│   │   └── __init__.py
│   ├── chat/                # チャット機能
│   │   └── __init__.py
│   ├── admin/               # 管理者機能
│   │   └── __init__.py
│   ├── models/              # データベースモデル
│   │   └── __init__.py
│   └── utils/               # ユーティリティ関数
│       ├── __init__.py
│       ├── validators.py
│       ├── datetime_helpers.py
│       ├── audit.py
│       ├── csv_helpers.py
│       ├── file_helpers.py
│       ├── email_helpers.py
│       └── git_helpers.py
├── run.py                   # 新しいメインエントリーポイント
├── app_old.py              # 元のapp.pyのバックアップ
└── utils_old.py            # 元のutils.pyのバックアップ
```

### 2. 起動方法の変更
**旧:**
```bash
python app.py
```

**新:**
```bash
python run.py
```

### 3. 主な改善点

#### セキュリティ
- CSRFトークン生成の自動化
- 入力検証の強化
- パスワード複雑度要件の追加
- HTMLエスケープの実装

#### コード品質
- 単一責任原則の適用
- コードの重複排除
- 関数の分割と整理
- 型ヒントとドキュメントの追加

#### パフォーマンス
- N+1クエリ対策の準備
- データベースアクセス層の分離
- エラーハンドリングの改善

#### 保守性
- 機能別モジュール分割
- 設定管理の統一
- ログ機能の強化

## 移行手順

### 1. 環境変数の確認
`.env`ファイルに以下の設定が必要です：
```
SECRET_KEY=your_secret_key_here
DB_PATH=database/kintai.db
FLASK_DEBUG=False
MAX_CONTENT_LENGTH=10485760
SESSION_LIFETIME_DAYS=7
AUDIT_LOG_PATH=logs/audit.log
```

### 2. 依存関係の確認
requirements.txtは変更されていませんが、新しい機能を使用する場合は追加パッケージが必要になる場合があります。

### 3. データベースの互換性
データベーススキーマに変更はありません。既存のデータはそのまま使用できます。

### 4. テンプレートの確認
テンプレートファイルは変更されていませんが、新しいCSRF保護機能を使用するために、フォームに以下を追加することを推奨します：
```html
<input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
```

## テスト結果
- ✅ アプリケーション作成成功
- ✅ モデルインポート成功
- ✅ ユーティリティ関数動作確認
- ✅ Blueprint登録成功

## ロールバック手順
問題が発生した場合の戻し方：

```bash
# バックアップファイルを元に戻す
mv app_old.py app.py
mv utils_old.py utils.py

# 新しいディレクトリを削除
rm -rf app/
rm run.py

# 元の方法で起動
python app.py
```

## 今後の開発
新しい機能を追加する際は、適切なモジュールに配置してください：
- 認証関連: `app/auth/`
- 勤怠管理: `app/attendance/`
- チャット機能: `app/chat/`
- 管理者機能: `app/admin/`
- データモデル: `app/models/`
- 共通機能: `app/utils/`

## 注意事項
1. 元のapp.pyとutils.pyはバックアップとして残してあります
2. 新しい構造で問題が発生した場合は、上記のロールバック手順を実行してください
3. 本格運用前に十分なテストを行ってください