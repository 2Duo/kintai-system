# 勤怠管理システム（Flask + SQLite）

このアプリケーションは、Flask と SQLite を用いた軽量な勤怠管理システムです。  
社員は出退勤の打刻や履歴の閲覧・修正ができ、管理者はユーザー管理やCSV出力などを行えます。

---

## 🔧 機能一覧

### 👤 一般ユーザー機能
- ログイン（メール + パスワード）
- 出退勤の手動打刻（時間入力可能、業務内容記録付き）
- 月間勤怠の閲覧・編集（1日1出勤・1退勤）
- 勤怠データのCSVインポート（確認ダイアログで差分選択）
- パスワードの変更

### 🚰 管理者機能
- ユーザー作成・編集・削除
- 管理対象ユーザーの設定（任意）
- 毎月5日のCSV自動生成（残業時間を含む）
- 任意ユーザー・任意月のCSV出力（ZIP一括も可80）
- エクスポートファイルのダウンロード
- ユーザーパスワードの再設定

---

## 📁 ディレクトリ構成
```
kintai-system/
├── app.py # Flaskアプリ本体
├── database/
│ ├── kintai.db # SQLite DBの実データ
│ └── schema.sql # テーブル定義
├── exports/ # 出力CSVの保存先
├── templates/ # HTMLテンプレート
├── static/
│ └── style.css # スタイルシート
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

python app.py  # 開発用（localhost:5000）
```

---

## 初回セットアップ

1. `http://localhost:5000/setup` にアクセス
2. 管理者アカウントを作成
3. ログイン後、ユーザー登録を実施

---

## 本番環境での常時運用（systemd+gunicorn）
gunicornで起動（確認用）
```
venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 app:app
```
systemd サービスファイル /etc/systemd/system/kintai.service
```ini
[Unit]
Description=Kintai System Flask App
After=network.target

[Service]
User=youruser
WorkingDirectory=/home/youruser/kintai-system
ExecStart=/home/youruser/kintai-system/venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```
有効化と起動
```bash
sudo systemctl daemon-reload
sudo systemctl enable kintai
sudo systemctl start kintai
```

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

---

## 技術スタック

- Python 3.x
- Flask
- SQLite3
- Bootstrap5（UIフレームワーク）

---

## ライセンス

MIT License
