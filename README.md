# 勤怠管理システム (Flask + SQLite)

Flask と SQLite を利用した小規模向け勤怠管理アプリケーションです。
従業員は Web ブラウザから出退勤の打刻や履歴編集ができ、管理者はユーザー管理や
データのエクスポートなどを行えます。

---

## 機能概要

### 一般ユーザー
- メールアドレスとパスワードによるログイン
- ログイン状態を一定期間保持
- 出退勤の手動打刻と業務内容の記録
- 勤怠履歴の閲覧・編集
- CSV データのインポート
- パスワード変更
- PWA 対応によるスマホ利用
- 管理者との 1 対 1 チャット (SSE でリアルタイム通知)

### 管理者
- ユーザーの作成・編集・削除
- 残業カウント開始時刻の設定
- 任意ユーザー・任意月の CSV 出力 (ZIP 一括可)
- エクスポートファイルのダウンロード
- ユーザーパスワードの再設定
- 管理対象ユーザーとのチャット
- (スーパー管理者) メールサーバー設定と監査ログ閲覧

---

## ディレクトリ構成
```
kintai-system/
├── app.py             # アプリケーション本体
├── database/          # DB 定義や作成済み DB
├── static/            # CSS/JS/アイコン等
├── templates/         # HTML テンプレート
├── tests/             # Pytest
└── ...
```

---

## セットアップ手順
1. リポジトリ取得と環境構築
   ```bash
   git clone https://github.com/2Duo/kintai-system.git
   cd kintai-system
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. `.env.example` をコピーして `.env` を作成し、`SECRET_KEY` を必ず変更します。
3. アプリを起動
   ```bash
   python app.py
   ```
   LAN 内の端末から `http://<IP アドレス>:8000` でアクセスできます。

---

## .env で管理する主な変数
| 変数名 | 説明 |
| --- | --- |
| `SECRET_KEY` | Flask セッション保護用キー |
| `DB_PATH` | SQLite データベースパス |
| `FLASK_DEBUG` | デバッグモードの ON/OFF |
| `MAX_CONTENT_LENGTH` | アップロード CSV の最大サイズ |
| `SESSION_LIFETIME_DAYS` | ログインを保持する日数 |
| `AUDIT_LOG_PATH` | 監査ログの保存先 |

---

## 本番運用例 (gunicorn + systemd)
```ini
[Unit]
Description=Kintai System
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/kintai-system
EnvironmentFile=/path/to/kintai-system/.env
ExecStart=/path/to/kintai-system/venv/bin/gunicorn -w 4 -k gevent -b 0.0.0.0:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```
`gevent` ワーカーを利用し、SSE エンドポイントに対応しています。

---

## CSV 形式
| 日付 | 出勤時刻 | 退勤時刻 | 業務内容 | 残業時間 |
| --- | --- | --- | --- | --- |
| 2025/05/17 | 09:00 | 18:40 | 設計業務 | 00:40 |
残業時間は各ユーザーの設定時刻を基準に計算されます。インポート用 CSV にこの列は不要です。

---

## セキュリティ上の注意
- `SECRET_KEY` は必ず独自に生成し、`.env` で管理してください。
- すべての POST フォームに CSRF トークンを自動挿入しています。
- CSV アップロードの拡張子とサイズを検証します。
- パスワードはハッシュ化して保存されます。
- 管理画面へのアクセス権限制御を実装しています。
- 本番運用時は必ず HTTPS で運用し、ファイルや DB の権限管理を厳格に行ってください。

---

## 技術スタック
- Python 3.x
- Flask
- SQLite
- Bootstrap 5
- PWA (manifest, service worker)

---

## ライセンス
MIT License
