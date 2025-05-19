# 勤怠管理システム（Flask + SQLite）

このアプリケーションは、Flask と SQLite を使用した軽量な勤怠管理システムです。  
社員は出退勤の打刻、履歴の閲覧・修正ができ、管理者はユーザー管理やCSV出力を行えます。

---

## 機能一覧

### 一般ユーザー機能
- ログイン（メール + パスワード）
- 出退勤打刻（手入力・時間編集可能、業務内容記録）
- 月間の勤怠表示・編集（1日1出勤・1退勤制限あり）
- 勤怠データのCSVインポート（確認ダイアログあり）

### 管理者機能
- ユーザー作成・管理
- 管理対象ユーザーの設定
- 勤怠CSVの自動生成（毎月5日）
- CSVの手動出力（任意日数 or 任意月単位）
- エクスポートファイルのダウンロード

---

## 構成

```
kintai-system/
├── app.py
├── database/
│   ├── kintai.db
│   └── schema.sql
├── exports/
│   └── *.csv（自動生成されたCSV）
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   └── ...（他の画面）
├── static/
│   └── style.css
└── README.md
```

---

## ▶起動方法

```bash
git clone https://github.com/2Duo/kintai-system.git
cd kintai-system
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python app.py
```

---

## 初回セットアップ

1. `http://localhost:5000/setup` にアクセス
2. 管理者アカウントを作成
3. ログイン後、ユーザー登録を実施

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

- 勤怠修正申請フロー（ユーザー→管理者承認）
- 勤務時間合計の表示
- モバイル対応のUI改善
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
