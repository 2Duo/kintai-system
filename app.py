from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
import sqlite3
from datetime import datetime, timedelta
import os
import csv
from io import StringIO, BytesIO, TextIOWrapper
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
import tempfile
import zipfile

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'kintai.db')
EXPORT_DIR = os.path.join(os.path.dirname(__file__), 'exports')
os.makedirs(EXPORT_DIR, exist_ok=True)

def initialize_database():
    if not os.path.exists(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        with open(os.path.join(os.path.dirname(__file__), 'database', 'schema.sql'), encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

initialize_database()

def safe_fromisoformat(ts):
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        parts = ts.split('T')
        if len(parts) == 2:
            date_part, time_part = parts
            if len(time_part.split(':')[0]) == 1:
                time_part = '0' + time_part
                ts = f"{date_part}T{time_part}"
        return datetime.fromisoformat(ts)

def normalize_time_str(time_str):
    # 例: "9:00" → "09:00"
    try:
        dt = datetime.strptime(time_str, '%H:%M')
        return dt.strftime('%H:%M')
    except ValueError:
        return time_str  # パースできない場合はそのまま返す

def generate_monthly_csv(year: int, month: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    c.execute("SELECT id, name, overtime_threshold FROM users")
    users = c.fetchall()

    for user_id, name, overtime_threshold in users:
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
            dt = safe_fromisoformat(ts)
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
            writer.writerow(['日付', '曜日', '出勤時刻', '退勤時刻', '業務内容', '残業時間'])

            for day in sorted(daily_data):
                data = daily_data[day]
                dt = datetime.strptime(day, '%Y/%m/%d')
                weekday = '月火水木金土日'[dt.weekday()]
                overtime = ''
                if data['out']:
                    try:
                        out_dt = datetime.strptime(data['out'], '%H:%M')
                        th_dt = datetime.strptime(overtime_threshold or '18:00', '%H:%M')
                        if out_dt > th_dt:
                            delta = out_dt - th_dt
                            h, m = divmod(delta.seconds // 60, 60)
                            overtime = f"{h:02d}:{m:02d}"
                    except:
                        pass
                writer.writerow([day, weekday, data['in'], data['out'], data['description'], overtime])
    conn.close()

def delete_old_exports(base_dir='exports', days=30):
    threshold = datetime.now() - timedelta(days=days)
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            path = os.path.join(root, file)
            if os.path.isfile(path) and os.path.getmtime(path) < threshold.timestamp():
                os.remove(path)

@app.before_request
def redirect_to_setup_if_first_run():
    if request.endpoint in ('static', 'setup'):
        return  # CSS や setup 自体には適用しない

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()

    if count == 0:
        return redirect(url_for('setup'))

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
        flash("CSVファイルを選択してください。", "danger")
        return redirect(url_for('view_my_logs'))

    try:
        temp_csv = TextIOWrapper(uploaded_file.stream, encoding='utf-8-sig')
        reader = csv.DictReader(temp_csv)
    except Exception:
        flash("CSVファイルの読み込みに失敗しました。フォーマットを確認してください。", "danger")
        return redirect(url_for('view_my_logs'))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 既存データの読み込み
    c.execute("SELECT timestamp, type, description FROM attendance WHERE user_id = ?", (user_id,))
    existing = defaultdict(dict)
    for ts, typ, desc in c.fetchall():
        dt = safe_fromisoformat(ts)
        day = dt.strftime('%Y-%m-%d')
        existing[day][typ] = (ts, desc)

    incoming = defaultdict(dict)
    try:
        for row in reader:
            raw_date = datetime.strptime(row['日付'], '%Y/%m/%d').strftime('%Y-%m-%d')
            desc = row.get('業務内容', '')
            if row.get('出勤時刻'):
                time = normalize_time_str(row['出勤時刻'])
                incoming[raw_date]['in'] = (f"{raw_date}T{time}:00", desc)
            if row.get('退勤時刻'):
                time = normalize_time_str(row['退勤時刻'])
                incoming[raw_date]['out'] = (f"{raw_date}T{time}:00", desc)
    except Exception:
        conn.close()
        flash("CSVデータの形式が正しくありません。日付・時刻形式を確認してください。", "danger")
        return redirect(url_for('view_my_logs'))

    # 衝突検出
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

    # 衝突なし → DB反映
    if not conflicts:
        for day in incoming:
            for typ in ['in', 'out']:
                if typ in incoming[day]:
                    ts, desc = incoming[day][typ]
                    c.execute("DELETE FROM attendance WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?",
                              (user_id, typ, day))
                    c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)",
                              (user_id, ts, typ, desc))
        conn.commit()
        conn.close()
        flash("CSVインポートが完了しました。", "success")
        return redirect(url_for('view_my_logs'))

    # 衝突あり → 確認画面へ
    conn.close()
    return render_template('resolve_conflicts.html', conflicts=conflicts, incoming=incoming, user_id=user_id, referer=request.referrer or url_for('view_my_logs'))

@app.route('/my/import/resolve', methods=['POST'])
def resolve_conflicts():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    referer = request.form.get('referer', url_for('view_my_logs'))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    errors = []
    updated_count = 0

    for key, value in request.form.items():
        if key.startswith("choice_"):
            try:
                _, day, typ = key.split("_", 2)
                choice = value  # 'existing' or 'incoming'

                if choice == 'incoming':
                    ts_key = f"incoming_ts_{day}_{typ}"
                    desc_key = f"incoming_desc_{day}_{typ}"

                    if ts_key not in request.form or not request.form[ts_key].strip():
                        errors.append(f"{day} の {typ}：時刻が指定されていません。")
                        continue

                    ts = request.form[ts_key]
                    desc = request.form.get(desc_key, '')

                    # 書き込み処理
                    c.execute("DELETE FROM attendance WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?",
                              (user_id, typ, day))
                    c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)",
                              (user_id, ts, typ, desc))
                    updated_count += 1

            except Exception as e:
                errors.append(f"{key} の処理中に予期しないエラーが発生しました。")

    conn.commit()
    conn.close()

    if errors:
        for msg in errors:
            flash(msg, "danger")
        return redirect(referer)

    flash(f"{updated_count} 件の勤怠データを更新しました。", "success")
    return redirect(referer)          

@app.route('/my/logs')
def view_my_logs():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ユーザーの残業しきい時刻を取得（例: '18:00'）
    c.execute("SELECT overtime_threshold FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    overtime_threshold = row[0] if row else '18:00'

    # 勤怠記録を取得
    c.execute("SELECT timestamp, type, description FROM attendance WHERE user_id = ? ORDER BY timestamp", (user_id,))
    records = c.fetchall()
    conn.close()

    attendance_by_day = {}
    for ts, typ, desc in records:
        dt = safe_fromisoformat(ts)
        date = dt.strftime('%Y-%m-%d')
        weekday = '月火水木金土日'[dt.weekday()]
        time = dt.strftime('%H:%M')
        if date not in attendance_by_day:
            attendance_by_day[date] = {'weekday': weekday, 'in': None, 'out': None, 'overtime': ''}
        attendance_by_day[date][typ] = {'time': time, 'description': desc}

    # 残業時間を日別に算出
    for date, data in attendance_by_day.items():
        if data['out']:
            out_time = data['out']['time']
            try:
                out_dt = datetime.strptime(out_time, '%H:%M')
                th_dt = datetime.strptime(overtime_threshold, '%H:%M')
                if out_dt > th_dt:
                    delta = out_dt - th_dt
                    hours, minutes = divmod(delta.seconds // 60, 60)
                    data['overtime'] = f"{hours:02d}:{minutes:02d}"
            except:
                data['overtime'] = ''
        else:
            data['overtime'] = ''

    return render_template('my_logs.html', logs=attendance_by_day)

@app.route('/my/logs/edit/<date>', methods=['GET', 'POST'])
def edit_log(date):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if request.method == 'POST':
        in_time = request.form.get('in_time')
        out_time = request.form.get('out_time')
        description = request.form.get('description')

        # 出勤削除＋再登録
        c.execute("DELETE FROM attendance WHERE user_id = ? AND type = 'in' AND substr(timestamp, 1, 10) = ?", (user_id, date))
        if in_time:
            c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, 'in', '')",
                      (user_id, f"{date}T{in_time}:00"))

        # 退勤削除＋再登録
        c.execute("DELETE FROM attendance WHERE user_id = ? AND type = 'out' AND substr(timestamp, 1, 10) = ?", (user_id, date))
        if out_time:
            c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, 'out', ?)",
                      (user_id, f"{date}T{out_time}:00", description or ''))

        conn.commit()
        conn.close()
        return redirect(url_for('view_my_logs'))

    # GET時は既存データを表示
    c.execute("""
        SELECT type, substr(timestamp, 12, 5), description FROM attendance
        WHERE user_id = ? AND substr(timestamp, 1, 10) = ?
    """, (user_id, date))
    rows = c.fetchall()
    conn.close()

    in_time = out_time = description = ''
    for typ, time, desc in rows:
        if typ == 'in':
            in_time = time
        elif typ == 'out':
            out_time = time
            description = desc or ''

    return render_template('edit_log.html', date=date, in_time=in_time, out_time=out_time, description=description)

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

        flash("メールアドレスまたはパスワードが正しくありません。", "danger")
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/admin/export', methods=['GET', 'POST'])
def export_combined():
    if not session.get('is_admin'):
        return 'アクセス拒否'
    admin_id = session['user_id']

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.name FROM users u
        INNER JOIN admin_managed_users m ON u.id = m.user_id
        WHERE m.admin_id = ?
        ORDER BY u.name
    """, (admin_id,))
    user_list = c.fetchall()
    conn.close()

    now = datetime.now()
    years = list(range(now.year - 3, now.year + 2))

    if request.method == 'POST':
        year = int(request.form['year'])
        month = int(request.form['month'])
        start = datetime(year, month, 1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)

        def generate_csv_for(user_id, name, target_dir):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            # 残業しきい時刻を取得（デフォルト: '18:00'）
            c.execute("SELECT overtime_threshold FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            overtime_threshold = row[0] if row and row[0] else '18:00'

            c.execute("""
                SELECT timestamp, type, description FROM attendance
                WHERE user_id = ? AND timestamp >= ? AND timestamp < ?
                ORDER BY timestamp ASC
            """, (user_id, start.isoformat(), end.isoformat()))
            rows = c.fetchall()
            conn.close()

            if not rows:
                return None

            daily_data = defaultdict(lambda: {'in': '', 'out': '', 'description': ''})
            for ts, typ, desc in rows:
                dt = safe_fromisoformat(ts)
                day = dt.strftime('%Y/%m/%d')
                time = dt.strftime('%H:%M')
                if typ == 'in':
                    daily_data[day]['in'] = time
                elif typ == 'out':
                    daily_data[day]['out'] = time
                    daily_data[day]['description'] = desc or ''

            filename = f"{name}_{year}_{month:02d}_勤怠記録.csv"
            filepath = os.path.join(target_dir, filename)
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['日付', '曜日', '出勤時刻', '退勤時刻', '業務内容', '残業時間'])

                for day in sorted(daily_data):
                    data = daily_data[day]
                    dt = datetime.strptime(day, '%Y/%m/%d')
                    weekday = '月火水木金土日'[dt.weekday()]

                    overtime = ''
                    if data['out']:
                        try:
                            out_dt = datetime.strptime(data['out'], '%H:%M')
                            th_dt = datetime.strptime(overtime_threshold, '%H:%M')
                            if out_dt > th_dt:
                                delta = out_dt - th_dt
                                h, m = divmod(delta.seconds // 60, 60)
                                overtime = f"{h:02d}:{m:02d}"
                        except:
                            pass

                    writer.writerow([day, weekday, data['in'], data['out'], data['description'], overtime])

            return filepath

        if request.form['action'] == 'single_user':
            user_id = int(request.form['user_id'])
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT name FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            conn.close()
            if not row:
                return 'ユーザーが見つかりません'
            name = row[0]

            export_subdir = os.path.join(EXPORT_DIR, f"{year}", f"{month:02d}")
            os.makedirs(export_subdir, exist_ok=True)
            csv_path = generate_csv_for(user_id, name, export_subdir)
            if not csv_path:
                return '該当データがありません'
            return send_file(csv_path, mimetype='text/csv', as_attachment=True, download_name=os.path.basename(csv_path))

        elif request.form['action'] == 'bulk_all':
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, f"勤怠記録_{year}_{month:02d}.zip")
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for user_id, name in user_list:
                        csv_file = generate_csv_for(user_id, name, temp_dir)
                        if csv_file:
                            zipf.write(csv_file, os.path.basename(csv_file))
                return send_file(zip_path, mimetype='application/zip', as_attachment=True, download_name=f"勤怠記録_{year}_{month:02d}.zip")

    return render_template('export.html', user_list=user_list, now=now, years=years)

@app.route('/admin/users')
def list_users():
    if not session.get('is_admin'):
        return 'アクセス拒否'
    admin_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, email, is_admin FROM users ORDER BY name")
    all_users = c.fetchall()
    c.execute("SELECT user_id FROM admin_managed_users WHERE admin_id = ?", (admin_id,))
    managed_ids = {row[0] for row in c.fetchall()}
    conn.close()

    users = []
    for user in all_users:
        users.append({
            'id_name': user,
            'is_managed': user[0] in managed_ids
        })

    return render_template('admin_users.html', users=users)

@app.route('/admin/users/create', methods=['GET', 'POST'])
def create_user():
    if not session.get('is_admin'):
        return 'アクセス拒否'

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        is_admin = int('is_admin' in request.form)
        password_hash = generate_password_hash(password)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (name, email, password_hash, is_admin) VALUES (?, ?, ?, ?)",
                      (name, email, password_hash, is_admin))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            flash("このメールアドレスはすでに登録されています。", "danger")
            return redirect(url_for('create_user'))

        conn.close()
        flash("ユーザーを作成しました。", "success")
        return redirect(url_for('list_users'))

    return render_template('create_user.html')

@app.route('/admin/users/manage', methods=['POST'])
def update_managed_users():
    if not session.get('is_admin'):
        return 'アクセス拒否'
    admin_id = session['user_id']
    selected_ids = request.form.getlist('managed_users')
    selected_ids = list(map(int, selected_ids))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 一旦削除して再登録
    c.execute("DELETE FROM admin_managed_users WHERE admin_id = ?", (admin_id,))
    for user_id in selected_ids:
        c.execute("INSERT INTO admin_managed_users (admin_id, user_id) VALUES (?, ?)", (admin_id, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for('list_users'))

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if not session.get('is_admin'):
        return 'アクセス拒否'

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip()
        is_admin = int('is_admin' in request.form)
        overtime_threshold = request.form.get('overtime_threshold', '18:00').strip()

        # バリデーション
        errors = []
        if not name:
            errors.append("氏名を入力してください。")
        if not email or "@" not in email:
            errors.append("正しいメールアドレスを入力してください。")
        try:
            datetime.strptime(overtime_threshold, '%H:%M')
        except ValueError:
            errors.append("残業開始時刻は HH:MM 形式で入力してください。")

        if errors:
            for msg in errors:
                flash(msg, "danger")
            conn.close()
            return redirect(url_for('edit_user', user_id=user_id))

        # 更新処理
        try:
            c.execute("UPDATE users SET name = ?, email = ?, is_admin = ?, overtime_threshold = ? WHERE id = ?",
                      (name, email, is_admin, overtime_threshold, user_id))
            conn.commit()
            flash("ユーザー情報を更新しました。", "success")
        except sqlite3.IntegrityError:
            flash("このメールアドレスは既に登録されています。", "danger")

        conn.close()
        return redirect(url_for('list_users'))

    c.execute("SELECT name, email, is_admin, overtime_threshold FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return render_template('edit_user.html', user_id=user_id, user=user)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not session.get('is_admin'):
        return 'アクセス拒否'
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('list_users'))

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
