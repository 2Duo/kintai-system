from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
from datetime import datetime, timedelta
import os
import csv
from io import StringIO, BytesIO, TextIOWrapper
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict


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
        daily_data = defaultdict(lambda: {'in': None, 'out': None, 'description': ''})
        for ts, typ, desc in rows:
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                parts = ts.split('T')
                if len(parts) == 2:
                    date_part, time_part = parts
                    if len(time_part.split(':')[0]) == 1:
                        time_part = '0' + time_part
                        ts = f"{date_part}T{time_part}"
                dt = datetime.fromisoformat(ts)
            day = dt.strftime('%Y/%m/%d')
            time = dt.strftime('%H:%M')
            if typ == 'in':
                daily_data[day]['in'] = time
            elif typ == 'out':
                daily_data[day]['out'] = time
            if typ == 'out' and desc:
                daily_data[day]['description'] = desc

        filename = f"{name}_{year}_{month:02d}_勤怠記録.csv"
        filepath = os.path.join(EXPORT_DIR, filename)
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['日付', '出勤時刻', '退勤時刻', '業務内容'])
            for day in sorted(daily_data):
                data = daily_data[day]
                writer.writerow([day, data['in'] or '', data['out'] or '', data['description']])
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
        if request.form.get('action') == 'generate_csv_now':
            now = datetime.now()
            generate_monthly_csv(now.year, now.month)
            return redirect(url_for('export_combined'))

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
        writer.writerow(['日付', '出勤時刻', '退勤時刻', '業務内容'])
        daily_data = defaultdict(lambda: {'in': '', 'out': '', 'description': ''})
        for ts, typ, desc in rows:
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                parts = ts.split('T')
                if len(parts) == 2:
                    date_part, time_part = parts
                    if len(time_part.split(':')[0]) == 1:
                        time_part = '0' + time_part
                        ts = f"{date_part}T{time_part}"
                dt = datetime.fromisoformat(ts)
            day = dt.strftime('%Y/%m/%d')
            time = dt.strftime('%H:%M')
            if typ == 'in':
                daily_data[day]['in'] = time
            elif typ == 'out':
                daily_data[day]['out'] = time
            if desc:
                daily_data[day]['description'] = desc
        for day in sorted(daily_data):
            data = daily_data[day]
            writer.writerow([day, data['in'], data['out'], data['description']])
        mem = BytesIO()
        mem.write(si.getvalue().encode('utf-8-sig'))
        mem.seek(0)
        filename = f"{name}_過去{days}日_勤怠記録.csv"
        return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=filename)

    files = os.listdir(EXPORT_DIR)
    files = [f for f in files if f.endswith('.csv')]
    files.sort(reverse=True)
    return render_template('export.html', files=files, user_names=user_names)

@app.route('/punch', methods=['POST'])
def punch():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    timestamp = request.form['timestamp']
    punch_type = request.form['type']
    description = request.form.get('description', '')

    day = timestamp[:10]  # YYYY-MM-DD
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT timestamp, description FROM attendance 
        WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?
    """, (user_id, punch_type, day))
    existing = c.fetchone()
    conn.close()

    if existing:
        return render_template('confirm_punch.html', existing={
        'timestamp': existing[0], 'description': existing[1]
    }, incoming={
        'timestamp': timestamp, 'description': description
    }, punch_type=punch_type, day=day, referer=request.referrer or url_for('index'))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)",
              (user_id, timestamp, punch_type, description))
    conn.commit()
    conn.close()
    referer = request.form.get('referer', url_for('index'))
    return redirect(referer)

@app.route('/punch/resolve', methods=['POST'])
def resolve_punch():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    action = request.form['action']
    day = request.form['day']
    punch_type = request.form['type']
    timestamp = request.form['timestamp']
    description = request.form.get('description', '')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if action == 'overwrite':
        c.execute("DELETE FROM attendance WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?",
                  (user_id, punch_type, day))
        c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)",
                  (user_id, timestamp, punch_type, description))
        conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/exports/<filename>')
def download_export_file(filename):
    if not session.get('is_admin'):
        return 'アクセス拒否'
    filepath = os.path.join(EXPORT_DIR, filename)
    if not os.path.isfile(filepath):
        return 'ファイルが存在しません'
    return send_file(filepath, as_attachment=True, mimetype='text/csv')

@app.route('/my/import', methods=['POST'])
def import_csv():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    uploaded_file = request.files['file']
    if not uploaded_file or not uploaded_file.filename.endswith('.csv'):
        return 'CSVファイルを選択してください'

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 既存データ読み込み
    c.execute("SELECT timestamp, type, description FROM attendance WHERE user_id = ?", (user_id,))
    existing = defaultdict(dict)
    for ts, typ, desc in c.fetchall():
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            parts = ts.split('T')
            if len(parts) == 2:
                date_part, time_part = parts
                if len(time_part.split(':')[0]) == 1:
                    time_part = '0' + time_part
                    ts = f"{date_part}T{time_part}"
            dt = datetime.fromisoformat(ts)
        day = dt.strftime('%Y-%m-%d')
        existing[day][typ] = (ts, desc)

    temp_csv = TextIOWrapper(uploaded_file.stream, encoding='utf-8-sig')
    reader = csv.DictReader(temp_csv)
    incoming = defaultdict(dict)
    for row in reader:
        raw_date = datetime.strptime(row['日付'], '%Y/%m/%d').strftime('%Y-%m-%d')
        desc = row.get('業務内容', '')
        if row.get('出勤時刻'):
            incoming[raw_date]['in'] = (f"{raw_date}T{row['出勤時刻']}:00", desc)
        if row.get('退勤時刻'):
            incoming[raw_date]['out'] = (f"{raw_date}T{row['退勤時刻']}:00", desc)

    conflicts = []
    for day in incoming:
        for typ in incoming[day]:
            if typ in existing.get(day, {}):
                conflicts.append({
                    'day': day,
                    'type': typ,
                    'existing': existing[day][typ],
                    'incoming': incoming[day][typ]
                })

    if not conflicts:
        for day in incoming:
            for typ in ['in', 'out']:
                if typ in incoming[day]:
                    ts, desc = incoming[day][typ]
                    c.execute("DELETE FROM attendance WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?", (user_id, typ, day))
                    c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)", (user_id, ts, typ, desc))
        conn.commit()
        conn.close()
        return redirect(url_for('view_my_logs'))

    conn.close()
    return render_template('resolve_conflicts.html', conflicts=conflicts, incoming=incoming, user_id=user_id, referer=request.referrer or url_for('view_my_logs'))

@app.route('/my/import/resolve', methods=['POST'])
def resolve_conflicts():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for key, value in request.form.items():
        if key.startswith("choice_"):
            _, day, typ = key.split("_", 2)
            choice = value  # 'existing' or 'incoming'
            if choice == 'incoming':
                ts = request.form[f"incoming_ts_{day}_{typ}"]
                desc = request.form.get(f"incoming_desc_{day}_{typ}", '')
                c.execute("DELETE FROM attendance WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?", (user_id, typ, day))
                c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)", (user_id, ts, typ, desc))
    conn.commit()
    conn.close()
    referer = request.form.get('referer', url_for('view_my_logs'))
    return redirect(referer)                    

@app.route('/my/logs')
def view_my_logs():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT timestamp, type, description FROM attendance WHERE user_id = ? ORDER BY timestamp", (user_id,))
    records = c.fetchall()
    conn.close()

    attendance_by_day = {}
    for ts, typ, desc in records:
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            parts = ts.split('T')
            if len(parts) == 2:
                date_part, time_part = parts
                if len(time_part.split(':')[0]) == 1:
                    time_part = '0' + time_part
                    ts = f"{date_part}T{time_part}"
            dt = datetime.fromisoformat(ts)
        date = dt.strftime('%Y-%m-%d')
        time = dt.strftime('%H:%M')
        if date not in attendance_by_day:
            attendance_by_day[date] = {'in': None, 'out': None}
        attendance_by_day[date][typ] = {'time': time, 'description': desc}

    return render_template('my_logs.html', logs=attendance_by_day)

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user_name=session['user_name'])

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
