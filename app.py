from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
from datetime import datetime, timedelta
import os
import csv
from io import StringIO, BytesIO
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'kintai.db')
EXPORT_DIR = os.path.join(os.path.dirname(__file__), 'exports')
os.makedirs(EXPORT_DIR, exist_ok=True)

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
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['日付', '時刻', '区分', '業務内容'])
            for ts, typ, desc in rows:
                dt = datetime.fromisoformat(ts)
                date_str = dt.strftime('%Y-%m-%d')
                time_str = dt.strftime('%H:%M')
                type_str = '出勤' if typ == 'in' else '退勤'
                writer.writerow([date_str, time_str, type_str, desc or ''])
    conn.close()

@app.route('/admin/export', methods=['GET', 'POST'])
def export_combined():
    if not session.get('is_admin'):
        return 'アクセス拒否'
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM users ORDER BY name")
    user_names = [row[0] for row in c.fetchall()]
    conn.close()
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
        mem = BytesIO()
        mem.write(si.getvalue().encode('utf-8-sig'))
        mem.seek(0)
        filename = f"{name}_過去{days}日_勤怠記録.csv"
        return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=filename)
    files = os.listdir(EXPORT_DIR)
    files = [f for f in files if f.endswith('.csv')]
    files.sort(reverse=True)
    return render_template('export.html', files=files, user_names=user_names)

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user_name=session['user_name'])

@app.route('/punch', methods=['POST'])
def punch():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    timestamp = request.form['timestamp']
    punch_type = request.form['type']
    description = request.form.get('description', '')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)", (user_id, timestamp, punch_type, description))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name, password_hash, is_admin FROM users WHERE email = ?", (email,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['is_admin'] = bool(user[3])
            return redirect(url_for('index'))
        return 'ログイン失敗'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin/create_user', methods=['GET', 'POST'])
def create_user():
    if not session.get('is_admin'):
        return 'アクセス拒否'
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        is_admin = 1 if 'is_admin' in request.form else 0
        password_hash = generate_password_hash(password)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (email, name, password_hash, is_admin) VALUES (?, ?, ?, ?)", (email, name, password_hash, is_admin))
            conn.commit()
        except sqlite3.IntegrityError:
            return 'メールアドレスは既に登録されています'
        finally:
            conn.close()
        return redirect(url_for('index'))
    return render_template('create_user.html')

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    if count > 0:
        conn.close()
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        password_hash = generate_password_hash(password)
        c.execute("INSERT INTO users (email, name, password_hash, is_admin) VALUES (?, ?, ?, 1)", (email, name, password_hash))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    conn.close()
    return render_template('setup.html')

if __name__ == '__main__':
    app.run(debug=True)
