# 勤怠管理システム（Flask + SQLite）

このアプリケーションは、Flask と SQLite を用いた軽量な勤怠管理システムです。  
社員は出退勤の打刻や履歴の閲覧・修正ができ、管理者はユーザー管理やCSV出力などを行えます。

---

## 機能一覧

### 一般ユーザー機能
- ログイン（メール + パスワード）
- 一定期間ブラウザを閉じてもログイン状態を保持
- 出退勤の手動打刻（時間入力可能、業務内容記録付き）
- 勤怠履歴の閲覧・編集（日別に1出勤・1退勤）
- 勤怠データのCSVインポート（確認ダイアログで差分選択）
- パスワードの変更
- スマホ・タブレットからの利用／PWAホーム追加
- 管理者との1対1チャット
  - WebSocketではなくServer-Sent Eventsで未読通知・新着メッセージを即時受信
  - 直近20件を表示し、スクロールすると過去の履歴を追加読み込み

### 管理者機能
- ユーザー作成・編集・削除
- 管理対象ユーザーの設定（任意）
- ユーザーごとの残業カウント開始時刻設定
- 任意ユーザー・任意月のCSV出力（ZIP一括も可）
- エクスポートファイルのダウンロード
- ユーザーパスワードの再設定
- 管理対象ユーザーとのチャット
  - Server-Sent Eventsでリアルタイム更新
  - 直近20件のみ表示し、上へスクロールすると追加取得
- （スーパー管理者）メールサーバー・通知文の設定
- （スーパー管理者）監査ログの閲覧
  - ログインや打刻時の操作履歴を記録する`.log`ファイルを表示・ダウンロードできます
  - サービス起動時にログは空になります
  - 端末種別（pc / smartphone / tablet）とOSを記録します

---

## ディレクトリ構成
```
kintai-system/
├── app.py # Flaskアプリ本体
├── database/
│ ├── kintai.db # SQLite DBの実データ（アプリ起動時に生成、Git管理外）
│ └── schema.sql # テーブル定義
├── exports/ # 出力CSVの保存先（アプリ実行時に自動生成されGit管理外）
├── templates/ # HTMLテンプレート
├── static/
│ ├── style.css # スタイルシート
│ ├── manifest.json # PWA用マニフェスト
│ ├── sw.js # サービスワーカー
│ ├── icon-192.png # PWA用アイコン
│ └── icon-512.png # PWA用アイコン
├── .env.example # 環境変数サンプル（公開可）
└── README.md
```

---

## ▶ ローカル開発環境での起動

```bash
git clone https://github.com/2Duo/kintai-system.git
cd kintai-system
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env.exampleをコピーして.envを作成・編集
cp .env.example .env
# .env内のSECRET_KEYは必ず独自のランダム値に変更してください

python app.py  # デフォルトでLAN内全デバイスからアクセス可（http://自分のIPアドレス:8000）
# SSE利用のため内部サーバーはスレッドモードで起動します
# Chromeの読み込み状態を解除する目的で、初回接続時に2KBのプレースホルダを送信しています
```

- 自分のPCのIPアドレスを確認し、同じネットワーク上のデバイスから`http://<IPアドレス>:8000`でアクセスできます。
- (`FLASK_DEBUG`環境変数により`debug`モードが切り替わることを確認)

---

## .envファイルによるシークレット管理

このプロジェクトでは**重要なシークレット情報（SECRET_KEYなど）を.envファイルで管理**します。  
**`.env.example`** が雛形として同梱されています。  
GitHub等にアップロードする際は、`.env`は**絶対に公開しないでください**（`.gitignore`推奨）。

### 1. .envファイルの作成方法

1. `.env.example` をコピーして `.env` を作成します。
2. 必ず `SECRET_KEY` の値を自分専用の安全なランダム値に**書き換えてください**。
   - 例：  
     ```
     SECRET_KEY=9dc53ed3bfe2c5d4727e70a9af1c02a13b7c05efabc29cf147e3ddc17e02f889
     ```
   - この値は**絶対にそのまま本番運用せず、自分で新しく生成してください**。
   - 生成例：Pythonで`import secrets; print(secrets.token_hex(32))`

### 2. Flaskアプリは起動時に自動で`.env`から環境変数を読み込みます

- `python-dotenv` を `requirements.txt` に含めています。
- アプリ起動時、`.env`の`SECRET_KEY`が自動でセットされます。

---

## PWA（ホーム画面追加・オフライン対応）について
- manifest.json, sw.js, アイコン画像（192px/512px）をstaticディレクトリに配置済み
- base.htmlにPWA用のタグ・スクリプトが挿入済み
- HTTPSでアクセスすると「ホーム画面に追加」や「インストール」が有効
- 一部ページ・静的リソースはオフラインでも閲覧可（sw.jsでキャッシュ制御）

---

## セキュリティ・運用上の注意

- **必ずSECRET_KEYを独自に生成し、.envファイルで安全に管理してください。**
- `.env` は **Gitリポジトリに含めず、`.gitignore`で除外**してください（`.env.example`のみ公開可）。
- **すべてのPOSTフォームにはCSRFトークンが自動挿入されます。**
- **ファイルアップロード（CSV）の拡張子制限・最大サイズ制限が有効です。**
    - `MAX_CONTENT_LENGTH` で上限を設定できます（デフォルト10MB）
    - 拡張子のチェックは `allowed_file` を参照
- **パスワードは8文字以上を必須とし、ハッシュ化保存しています。**
- **管理画面のアクセス権限制御が有効です。**
- **本番運用時は必ずHTTPS（SSL/TLS）で運用してください。**
- **DB・エクスポートCSV・ログなどは外部に漏れないようパーミッション管理を厳格に。**

---

## 環境変数例

- `SECRET_KEY` ... Flaskセッション保護用（本番ではランダムな値に必ず変更）
- `DB_PATH` ... SQLiteデータベースパス（必要に応じて環境ごとに変更）
- `FLASK_DEBUG` ... `1` でデバッグモード有効（未設定・0で無効）
- `MAX_CONTENT_LENGTH` ... アップロード可能なCSVの最大バイト数（例: 10485760）
- `SESSION_LIFETIME_DAYS` ... ログイン状態を保持する日数（例: 7）
- `AUDIT_LOG_PATH` ... 監査ログファイルの出力パス（省略時は `logs/audit.log`）
  - 行は `timestamp\taction\tuser_id\tuser_name\tIP\tdevice\tOS` の形式
    - `device` は `pc` / `smartphone` / `tablet`
    - `timestamp` は `YYYY-MM-DD HH:MM:SS`

---

## Ubuntuでの常駐運用例（gunicorn + systemd）

1. 仮想環境を作成し、依存パッケージをインストールします。
   ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  # gevent もここでインストールされます
  ```
2. `.env.example` をコピーして `.env` を作成し、`SECRET_KEY` や `FLASK_DEBUG=0` など本番用の値を設定します。
3. `gunicorn` でアプリを起動する systemd サービスファイルを作成します。例：`/etc/systemd/system/kintai.service`
   ```ini
   [Unit]
   Description=Kintai System
   After=network.target

   [Service]
   Type=simple
   User=www-data  # 実行ユーザー
   WorkingDirectory=/path/to/kintai-system
   EnvironmentFile=/path/to/kintai-system/.env
   ExecStart=/path/to/kintai-system/venv/bin/gunicorn -w 4 -k gevent -b 0.0.0.0:8000 app:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
ここでは長時間接続が必要なSSEエンドポイントに対応するため、`-k gevent` オプションで非同期ワーカーを利用しています。
4. サービスを有効化・起動します。
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start kintai.service
   sudo systemctl enable kintai.service
   ```
   `systemctl status kintai.service` で状態を確認できます。


---

## CSV仕様

### 出力形式（例）

| 日付       | 出勤時刻 | 退勤時刻 | 業務内容     | 残業時間 |
|------------|-----------|-----------|----------------|----------|
| 2025/05/17 | 09:00     | 18:40     | 設計業務 | 00:40    |

- 残業時間は各ユーザーの設定時刻（例：18:00）を基準に計算されます。
- インポートCSVには残業時間列は不要です。

---

## 今後の予定

（なし）

---

## 技術スタック

- Python 3.x
- Flask
- SQLite3
- Bootstrap5（UIフレームワーク）
- PWA（manifest, service worker, アイコン）
- ChatGPT

---

## ライセンス

MIT License
