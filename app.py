from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
from datetime import datetime, timedelta
import os
import csv
from io import StringIO
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # セッション管理に必要

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'kintai.db')
EXPORT_DIR = os.path.join(os.path.dirname(__file__), 'exports')
os.makedirs(EXPORT_DIR, exist_ok=True)

# Ensure DB exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0
)''')
c.execute('''CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    type TEXT CHECK(type IN ('in','out')) NOT NULL,
    description TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
)''')
conn.commit()
conn.close()

def generate_monthly_csv(year: int, month: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    c.execute("SELECT id, name FROM users")
    users = c.fetchall()

    for user_id, name in users:
        c.execute("""
            SELECT timestamp, type, description FROM attendance
            WHERE user_id = ? AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
        """, (user_id, start.isoformat(), end.isoformat()))
        rows = c.fetchall()

        if not rows:
            continue

        filename = f"{name}_{year}_{month:02d}_勤怠記録.csv"
        filepath = os.path.join(EXPORT_DIR, filename)
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['日付', '時刻', '区分', '業務内容'])
            for ts, typ, desc in rows:
                dt = datetime.fromisoformat(ts)
                date_str = dt.strftime('%Y-%m-%d')
                time_str = dt.strftime('%H:%M')
                type_str = '出勤' if typ == 'in' else '退勤'
                writer.writerow([date_str, time_str, type_str, desc or ''])
    conn.close()

@app.route('/admin/export_days', methods=['GET', 'POST'])
def export_days():
    if not session.get('is_admin'):
        return 'アクセス拒否'
    if request.method == 'POST':
        name = request.form['name']
        days = int(request.form['days'])
        end = datetime.now()
        start = end - timedelta(days=days)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE name = ?", (name,))
        user = c.fetchone()
        if not user:
            conn.close()
            return 'ユーザーが見つかりません'

        user_id = user[0]
        c.execute("""
            SELECT timestamp, type, description FROM attendance
            WHERE user_id = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (user_id, start.isoformat(), end.isoformat()))
        rows = c.fetchall()
        conn.close()

        if not rows:
            return '該当データがありません'

        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(['日付', '時刻', '区分', '業務内容'])
        for ts, typ, desc in rows:
            dt = datetime.fromisoformat(ts)
            date_str = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M')
            type_str = '出勤' if typ == 'in' else '退勤'
            writer.writerow([date_str, time_str, type_str, desc or ''])

        si.seek(0)
        filename = f"{name}_過去{days}日_勤怠記録.csv"
        return send_file(
            si,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename,
            encoding='utf-8'
        )

    return '''
    <form method="post">
        氏名: <input type="text" name="name"><br>
        過去何日分: <input type="number" name="days"><br>
        <button type="submit">CSV生成してダウンロード</button>
    </form>
    '''
