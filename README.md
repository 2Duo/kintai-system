# 勤怠管理システム（Flask + SQLite）

このアプリケーションは、Flask と SQLite を用いた軽量な勤怠管理システムです。  
社員は出退勤の打刻や履歴の閲覧・修正ができ、管理者はユーザー管理やCSV出力などを行えます。

---

## 機能一覧

### 一般ユーザー機能
- ログイン（メール + パスワード）
- 出退勤の手動打刻（時間入力可能、業務内容記録付き）
- 月間勤怠の閲覧・編集（1日1出勤・1退勤）
- 勤怠データのCSVインポート（確認ダイアログで差分選択）
- パスワードの変更
- スマホ・タブレットからの利用／PWAホーム追加

### 管理者機能
- ユーザー作成・編集・削除
- 管理対象ユーザーの設定（任意）
- 毎月5日のCSV自動生成（残業時間を含む）
- 任意ユーザー・任意月のCSV出力（ZIP一括も可80）
- エクスポートファイルのダウンロード
- ユーザーパスワードの再設定

---

## ディレクトリ構成
```
kintai-system/
├── app.py # Flaskアプリ本体
├── database/
│ ├── kintai.db # SQLite DBの実データ
│ └── schema.sql # テーブル定義
├── exports/ # 出力CSVの保存先
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
```

- 自分のPCのIPアドレスを確認し、同じネットワーク上のデバイスから`http://<IPアドレス>:8000`でアクセスできます。
- (`app.py`の最後が`app.run(host='0.0.0.0', port=8000, debug=True)`であることを確認)

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
    - デフォルトでは10MB以内推奨、app.pyの`allowed_file`参照
- **パスワードは8文字以上を必須とし、ハッシュ化保存しています。**
- **管理画面のアクセス権限制御が有効です。**
- **本番運用時は必ずHTTPS（SSL/TLS）で運用してください。**
- **DB・エクスポートCSV・ログなどは外部に漏れないようパーミッション管理を厳格に。**

---

## 環境変数例

- `SECRET_KEY` ... Flaskセッション保護用（本番ではランダムな値に必ず変更）
- `DB_PATH` ... SQLiteデータベースパス（必要に応じて環境ごとに変更）

---

## CSV仕様

### 出力形式（例）

| 日付       | 出勤時刻 | 退勤時刻 | 業務内容     | 残業時間 |
|------------|-----------|-----------|----------------|----------|
| 2025/05/17 | 09:00     | 18:40     | コーティング作業 | 00:40    |

- 残業時間は各ユーザーの設定時刻（例：18:00）を基準に計算されます。
- インポートCSVには残業時間列は不要です。

---

## 今後の予定

- 勤務時間合計の表示
- 監査ログの記録（IP・端末など）
- PWAのオフライン機能拡充（例：オフライン打刻→復帰時同期）

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
