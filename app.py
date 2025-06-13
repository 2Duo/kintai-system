from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from werkzeug.exceptions import RequestEntityTooLarge
import sqlite3
from datetime import datetime, timedelta
import os
import csv
from io import TextIOWrapper
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
import tempfile
import zipfile
import re
import secrets
from functools import wraps
from dotenv import load_dotenv
import smtplib
from email.message import EmailMessage
import subprocess

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key_here')  # 本番は環境変数
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024))

if not app.secret_key or app.secret_key == 'your_secret_key_here':
    raise RuntimeError("SECRET_KEYを環境変数で必ず設定してください")

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'kintai.db')
EXPORT_DIR = os.path.join(os.path.dirname(__file__), 'exports')
os.makedirs(EXPORT_DIR, exist_ok=True)

# 監査ログ設定
AUDIT_LOG_PATH = os.environ.get(
    'AUDIT_LOG_PATH',
    os.path.join(os.path.dirname(__file__), 'logs', 'audit.log')
)
os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)

def clear_audit_log():
    """サービス起動時に監査ログを空にする"""
    with open(AUDIT_LOG_PATH, 'w', encoding='utf-8'):
        pass

clear_audit_log()

# === 1. 共通DBコネクション関数 ===
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# === 2. バリデーション関数 ===
def is_valid_email(email):
    return bool(re.match(r'^[^@]+@[^@]+\.[^@]+$', email))

def is_valid_time(time_str):
    try:
        datetime.strptime(time_str, '%H:%M')
        return True
    except ValueError:
        return False

# === 2b. 監査ログ ===
def get_client_info(ua):
    """User-Agent から端末種別とOS名を推測する"""
    ua_lower = (ua or '').lower()
    if 'android' in ua_lower:
        os_name = 'Android'
    elif 'iphone' in ua_lower or 'ipad' in ua_lower or 'ios' in ua_lower:
        os_name = 'iOS'
    elif 'windows' in ua_lower:
        os_name = 'Windows'
    elif 'mac os x' in ua_lower or 'macintosh' in ua_lower:
        os_name = 'macOS'
    elif 'linux' in ua_lower:
        os_name = 'Linux'
    else:
        os_name = '-'

    if 'ipad' in ua_lower or 'tablet' in ua_lower or ('android' in ua_lower and 'mobile' not in ua_lower):
        device = 'tablet'
    elif 'iphone' in ua_lower or ('android' in ua_lower and 'mobile' in ua_lower):
        device = 'smartphone'
    else:
        device = 'pc'
    return device, os_name

def log_audit_event(action, user_id=None, user_name=None):
    """監査ログにイベントを記録する"""
    ip = request.remote_addr or '-'
    ua = request.headers.get('User-Agent', '')
    device, os_name = get_client_info(ua)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = (
        f"{ts}\t{action}\t{user_id if user_id else '-'}\t"
        f"{user_name if user_name else '-'}\t{ip}\t{device}\t{os_name}\n"
    )
    with open(AUDIT_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line)

# === 3. CSRFトークン管理 ===
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']
app.jinja_env.globals['csrf_token'] = generate_csrf_token

def check_csrf():
    if request.method == 'POST':
        token = request.form.get('_csrf_token')
        if not token or session.get('_csrf_token') != token:
            flash("セッションエラーが発生しました。やり直してください。", "danger")
            return False
    return True


@app.context_processor
def inject_unread_count():
    if 'user_id' not in session:
        return {'unread_count': 0}
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM messages WHERE recipient_id = ? AND is_read = 0",
        (session['user_id'],),
    )
    count = c.fetchone()[0]
    conn.close()
    return {'unread_count': count}

# === 4. ログイン/権限チェックデコレーター ===
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return 'アクセス拒否'
        return f(*args, **kwargs)
    return decorated

def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_superadmin'):
            return 'アクセス拒否'
        return f(*args, **kwargs)
    return decorated

# embedded=1 を維持したままリダイレクトするユーティリティ
def redirect_embedded(endpoint, **values):
    embedded = request.args.get('embedded') or request.form.get('embedded')
    if embedded:
        values['embedded'] = embedded
    return redirect(url_for(endpoint, **values))

# === 5. ファイル検証 ===
ALLOWED_EXTENSIONS = {'csv'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# === 6. エラーハンドリング ===
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    flash("アップロードできるファイルサイズを超えています。", "danger")
    return redirect(url_for('view_my_logs')), 413

# === 7. DB初期化 ===
def initialize_database():
    if not os.path.exists(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        with open(os.path.join(os.path.dirname(__file__), 'database', 'schema.sql'), encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
initialize_database()

# === 8. 各種ユーティリティ ===
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
    try:
        dt = datetime.strptime(time_str, '%H:%M')
        return dt.strftime('%H:%M')
    except ValueError:
        return time_str

def calculate_overtime(out_time, threshold='18:00'):
    """Calculate overtime string from out_time and threshold."""
    try:
        out_dt = datetime.strptime(out_time, '%H:%M')
        th_dt = datetime.strptime(threshold or '18:00', '%H:%M')
        if out_dt > th_dt:
            delta = out_dt - th_dt
            hours, minutes = divmod(delta.seconds // 60, 60)
            return f"{hours:02d}:{minutes:02d}"
    except ValueError:
        return ''
    return ''

def fetch_overtime_threshold(user_id, default='18:00'):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT overtime_threshold FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row['overtime_threshold'] if row and row['overtime_threshold'] else default

# === 8.1 メール設定管理 ===
def get_mail_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT server, port, username, password, use_tls, subject_template, body_template FROM mail_settings WHERE id = 1"
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def save_mail_settings(server, port, username, password, use_tls, subject_tmpl, body_tmpl):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO mail_settings (id, server, port, username, password, use_tls, subject_template, body_template)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            server=excluded.server,
            port=excluded.port,
            username=excluded.username,
            password=excluded.password,
            use_tls=excluded.use_tls,
            subject_template=excluded.subject_template,
            body_template=excluded.body_template
        """,
        (server, port, username, password, use_tls, subject_tmpl, body_tmpl),
    )
    conn.commit()
    conn.close()


def send_registration_email(to_email, name):
    settings = get_mail_settings()
    if not settings:
        return
    subject = (settings.get("subject_template") or "").format(name=name, email=to_email)
    body = (settings.get("body_template") or "").format(name=name, email=to_email)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.get("username") or settings.get("server")
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings["server"], int(settings["port"])) as smtp:
            if settings.get("use_tls"):
                smtp.starttls()
            if settings.get("username"):
                smtp.login(settings["username"], settings.get("password", ""))
            smtp.send_message(msg)
    except Exception as e:
        app.logger.error(f"メール送信に失敗しました: {e}")


# === 8.2 アップデート管理 ===

def get_git_commits():
    """ローカルとリモートの最新コミットを取得する"""
    try:
        local = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None, None
    try:
        subprocess.run(['git', 'fetch'], capture_output=True, text=True, check=True)
        remote = subprocess.run(['git', 'rev-parse', 'origin/main'], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        remote = None
    return local, remote

def get_changed_files():
    """リモートとの差分ファイル一覧を取得する"""
    try:
        subprocess.run(['git', 'fetch'], capture_output=True, text=True, check=True)
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD', 'origin/main'],
            capture_output=True, text=True, check=True
        )
        files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        return files
    except Exception:
        return None

def perform_git_pull():
    try:
        result = subprocess.run(['git', 'pull', '--ff-only'], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        return str(e)

# === 9. CSV出力ロジック一本化 ===
def generate_csv(user_id, name, year, month, target_dir, overtime_threshold='18:00'):
    conn = get_db()
    c = conn.cursor()
    start = datetime(year, month, 1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
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
    for row in rows:
        ts, typ, desc = row
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
            overtime = calculate_overtime(data['out'], overtime_threshold) if data['out'] else ''
            writer.writerow([day, weekday, data['in'], data['out'], data['description'], overtime])
    return filepath

def delete_old_exports(base_dir='exports', days=30):
    threshold = datetime.now() - timedelta(days=days)
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            path = os.path.join(root, file)
            if os.path.isfile(path) and os.path.getmtime(path) < threshold.timestamp():
                os.remove(path)

# === 10. 初回起動時セットアップ画面リダイレクト ===
@app.before_request
def redirect_to_setup_if_first_run():
    if app.config.get('TESTING'):
        return
    if request.endpoint in ('static', 'setup'):
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    if count == 0:
        return redirect(url_for('setup'))

# === 11. 各route ===

@app.route('/')
@login_required
def index():
    return render_template('index.html', user_name=session['user_name'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    errors = {}
    if request.method == 'POST':
        if not check_csrf():
            return redirect(url_for('login'))
        email = request.form.get('email', '')
        password = request.form.get('password', '')

        if not email:
            errors['email'] = "メールアドレスを入力してください。"
        if not password:
            errors['password'] = "パスワードを入力してください。"

        user = None
        if not errors:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT id, name, password_hash, is_admin, is_superadmin FROM users WHERE email = ?", (email,))
            user = c.fetchone()
            conn.close()
            if not user or not check_password_hash(user['password_hash'], password):
                errors['password'] = "メールアドレスまたはパスワードが正しくありません。"

        if errors:
            return render_template('login.html', errors=errors)
        
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['is_admin'] = bool(user['is_admin'])
        session['is_superadmin'] = bool(user['is_superadmin'])
        log_audit_event('login', user['id'], user['name'])
        return redirect(url_for('index'))

    return render_template('login.html', errors=errors)

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    user_name = session.get('user_name')
    session.clear()
    if user_id:
        log_audit_event('logout', user_id, user_name)
    return redirect(url_for('login'))

@app.route('/punch', methods=['POST'])
@login_required
def punch():
    if not check_csrf():
        return redirect(url_for('index'))
    user_id = session['user_id']
    timestamp = request.form['timestamp']
    punch_type = request.form['type']
    description = request.form.get('description', '')
    day = timestamp[:10]
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, description FROM attendance 
        WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?
    """, (user_id, punch_type, day))
    existing = c.fetchone()
    conn.close()
    if existing:
        return render_template('confirm_punch.html', existing={
            'timestamp': existing['timestamp'], 'description': existing['description']
        }, incoming={
            'timestamp': timestamp, 'description': description
        }, punch_type=punch_type, day=day, referer=request.referrer or url_for('index'))
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)",
              (user_id, timestamp, punch_type, description))
    conn.commit()
    conn.close()
    log_audit_event(f'punch:{punch_type}', user_id, session.get('user_name'))
    flash("打刻しました。", "success")
    referer = request.form.get('referer', url_for('index'))
    return redirect(referer)

@app.route('/punch/resolve', methods=['POST'])
@login_required
def resolve_punch():
    if not check_csrf():
        return redirect(url_for('index'))
    user_id = session['user_id']
    action = request.form['action']
    day = request.form['day']
    punch_type = request.form['type']
    timestamp = request.form['timestamp']
    description = request.form.get('description', '')
    conn = get_db()
    c = conn.cursor()
    if action == 'overwrite':
        c.execute("DELETE FROM attendance WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?",
                  (user_id, punch_type, day))
        c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)",
                  (user_id, timestamp, punch_type, description))
        conn.commit()
    conn.close()
    log_audit_event(
        f'resolve:{action}:{punch_type}', user_id, session.get('user_name')
    )
    flash("打刻しました。", "success")
    referer = request.form.get('referer', url_for('index'))
    return redirect(referer)

@app.route('/exports/<path:filename>')
@admin_required
def download_export_file(filename):
    export_root = os.path.abspath(EXPORT_DIR)
    filepath = os.path.abspath(os.path.join(EXPORT_DIR, filename))
    if not filepath.startswith(export_root + os.sep):
        return '不正なファイルパスです', 400
    if not os.path.isfile(filepath):
        return 'ファイルが存在しません', 404
    return send_file(filepath, as_attachment=True, mimetype='text/csv')

@app.route('/my')
@login_required
def my_page():
    return render_template('my_dashboard.html')


@app.route('/my/profile')
@login_required
def my_profile():
    return render_template('my_profile.html')


@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/my/password', methods=['GET', 'POST'])
@login_required
def my_password():
    user_id = session['user_id']
    errors = {}
    if request.method == 'POST':
        if not check_csrf():
            return redirect_embedded('my_password')
        current = request.form.get('current_password', '')
        new = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        if not current:
            errors['current_password'] = "現在のパスワードを入力してください。"
        if not new:
            errors['new_password'] = "新しいパスワードを入力してください。"
        elif len(new) < 8:
            errors['new_password'] = "パスワードは8文字以上で入力してください。"
        if not confirm:
            errors['confirm_password'] = "新しいパスワード（確認）を入力してください。"
        elif new and new != confirm:
            errors['confirm_password'] = "新しいパスワードが一致しません。"

        if not errors:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            if not row or not check_password_hash(row['password_hash'], current):
                errors['current_password'] = "現在のパスワードが正しくありません。"
                conn.close()
            else:
                new_hash = generate_password_hash(new)
                c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
                conn.commit()
                conn.close()
                flash("パスワードを更新しました。", "success")
                return redirect_embedded('my_password')

        return render_template('my_password.html', errors=errors)

    return render_template('my_password.html', errors=errors)

@app.route('/my/import', methods=['POST'])
@login_required
def import_csv():
    if not check_csrf():
        return redirect(url_for('view_my_logs'))
    user_id = session['user_id']
    uploaded_file = request.files['file']
    if not uploaded_file or not allowed_file(uploaded_file.filename):
        flash("CSVファイルのみアップロードできます。", "danger")
        return redirect(url_for('view_my_logs'))
    try:
        temp_csv = TextIOWrapper(uploaded_file.stream, encoding='utf-8-sig')
        reader = csv.DictReader(temp_csv)
    except Exception:
        flash("CSVファイルの読み込みに失敗しました。フォーマットを確認してください。", "danger")
        return redirect(url_for('view_my_logs'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT timestamp, type, description FROM attendance WHERE user_id = ?", (user_id,))
    existing = defaultdict(dict)
    for row in c.fetchall():
        ts, typ, desc = row
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
                    c.execute("DELETE FROM attendance WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?",
                              (user_id, typ, day))
                    c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)",
                              (user_id, ts, typ, desc))
        conn.commit()
        conn.close()
        flash("CSVインポートが完了しました。", "success")
        return redirect(url_for('view_my_logs'))
    conn.close()
    return render_template('resolve_conflicts.html', conflicts=conflicts, incoming=incoming, user_id=user_id, referer=request.referrer or url_for('view_my_logs'))

@app.route('/my/import/resolve', methods=['POST'])
@login_required
def resolve_conflicts():
    if not check_csrf():
        return redirect(url_for('view_my_logs'))
    user_id = session['user_id']
    referer = request.form.get('referer', url_for('view_my_logs'))
    conn = get_db()
    c = conn.cursor()
    errors = []
    updated_count = 0
    for key, value in request.form.items():
        if key.startswith("choice_"):
            try:
                _, day, typ = key.split("_", 2)
                choice = value
                if choice == 'incoming':
                    ts_key = f"incoming_ts_{day}_{typ}"
                    desc_key = f"incoming_desc_{day}_{typ}"
                    if ts_key not in request.form or not request.form[ts_key].strip():
                        errors.append(f"{day} の {typ}：時刻が指定されていません。")
                        continue
                    ts = request.form[ts_key]
                    desc = request.form.get(desc_key, '')
                    c.execute("DELETE FROM attendance WHERE user_id = ? AND type = ? AND substr(timestamp, 1, 10) = ?",
                              (user_id, typ, day))
                    c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, ?, ?)",
                              (user_id, ts, typ, desc))
                    updated_count += 1
            except Exception:
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
@login_required
def view_my_logs():
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    overtime_threshold = fetch_overtime_threshold(user_id)
    c.execute("SELECT timestamp, type, description FROM attendance WHERE user_id = ? ORDER BY timestamp", (user_id,))
    records = c.fetchall()
    conn.close()
    attendance_by_day = {}
    for row in records:
        ts, typ, desc = row
        dt = safe_fromisoformat(ts)
        date = dt.strftime('%Y-%m-%d')
        weekday = '月火水木金土日'[dt.weekday()]
        time = dt.strftime('%H:%M')
        if date not in attendance_by_day:
            attendance_by_day[date] = {'weekday': weekday, 'in': None, 'out': None, 'overtime': ''}
        attendance_by_day[date][typ] = {'time': time, 'description': desc}
    for date, data in attendance_by_day.items():
        if data['out']:
            data['overtime'] = calculate_overtime(data['out']['time'], overtime_threshold)
        else:
            data['overtime'] = ''
    return render_template('my_logs.html', logs=attendance_by_day)

@app.route('/my/logs/edit/<date>', methods=['GET', 'POST'])
@login_required
def edit_log(date):
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        if not check_csrf():
            return redirect(url_for('edit_log', date=date))
        in_time = request.form.get('in_time')
        out_time = request.form.get('out_time')
        description = request.form.get('description')
        c.execute("DELETE FROM attendance WHERE user_id = ? AND type = 'in' AND substr(timestamp, 1, 10) = ?", (user_id, date))
        if in_time:
            c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, 'in', '')",
                      (user_id, f"{date}T{in_time}:00"))
        c.execute("DELETE FROM attendance WHERE user_id = ? AND type = 'out' AND substr(timestamp, 1, 10) = ?", (user_id, date))
        if out_time:
            c.execute("INSERT INTO attendance (user_id, timestamp, type, description) VALUES (?, ?, 'out', ?)",
                      (user_id, f"{date}T{out_time}:00", description or ''))
        conn.commit()
        conn.close()
        return redirect(url_for('view_my_logs'))
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


def can_chat(current_id, partner_id):
    conn = get_db()
    c = conn.cursor()
    if session.get('is_admin'):
        c.execute(
            "SELECT 1 FROM admin_managed_users WHERE admin_id = ? AND user_id = ?",
            (current_id, partner_id),
        )
    else:
        c.execute(
            "SELECT 1 FROM admin_managed_users WHERE admin_id = ? AND user_id = ?",
            (partner_id, current_id),
        )
    allowed = c.fetchone() is not None
    conn.close()
    return allowed


def fetch_user_name(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row['name'] if row else ''


@app.route('/chat/<int:partner_id>', methods=['GET', 'POST'])
@login_required
def chat(partner_id):
    current_id = session['user_id']
    if not can_chat(current_id, partner_id):
        return 'アクセス拒否'
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        if not check_csrf():
            conn.close()
            return redirect(url_for('chat', partner_id=partner_id))
        message = request.form.get('message', '').strip()
        if message:
            c.execute(
                "INSERT INTO messages (sender_id, recipient_id, message, timestamp)"
                " VALUES (?, ?, ?, ?)",
                (
                    current_id,
                    partner_id,
                    message,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ),
            )
            conn.commit()
    c.execute(
        """
        SELECT id, sender_id, recipient_id, message, timestamp, is_read, read_timestamp
        FROM messages
        WHERE (sender_id = ? AND recipient_id = ?) OR
              (sender_id = ? AND recipient_id = ?)
        ORDER BY timestamp
        """,
        (current_id, partner_id, partner_id, current_id),
    )
    messages = c.fetchall()
    last_read = ''
    for m in messages:
        rt = m['read_timestamp']
        if rt and rt > last_read:
            last_read = rt
    conn.close()
    partner_name = fetch_user_name(partner_id)
    return render_template(
        'chat.html',
        messages=messages,
        partner_id=partner_id,
        partner_name=partner_name,
        current_id=current_id,
        last_read=last_read,
    )


@app.route('/chat/poll/<int:partner_id>')
@login_required
def poll_chat(partner_id):
    current_id = session['user_id']
    if not can_chat(current_id, partner_id):
        return {'messages': [], 'reads': []}
    after = request.args.get('after', '1970-01-01 00:00:00')
    after_read = request.args.get('after_read', '1970-01-01 00:00:00')
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, sender_id, recipient_id, message, timestamp, is_read, read_timestamp
        FROM messages
        WHERE ((sender_id = ? AND recipient_id = ?) OR
               (sender_id = ? AND recipient_id = ?)) AND timestamp > ?
        ORDER BY timestamp
        """,
        (current_id, partner_id, partner_id, current_id, after),
    )
    rows = [dict(r) for r in c.fetchall()]
    c.execute(
        "SELECT id FROM messages WHERE sender_id = ? AND recipient_id = ? AND is_read = 1 AND read_timestamp > ?",
        (current_id, partner_id, after_read),
    )
    read_ids = [r['id'] for r in c.fetchall()]
    conn.close()
    return {'messages': rows, 'reads': read_ids}


@app.route('/chat/mark_read/<int:partner_id>', methods=['POST'])
@login_required
def mark_chat_read(partner_id):
    if not can_chat(session['user_id'], partner_id):
        return {'status': 'error'}, 403
    if not check_csrf():
        return {'status': 'error'}, 400
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE messages SET is_read = 1, read_timestamp = ? WHERE sender_id = ? AND recipient_id = ? AND is_read = 0",
        (now, partner_id, session['user_id']),
    )
    updated = c.rowcount
    conn.commit()
    conn.close()
    return {'updated': updated, 'ts': now}


@app.route('/chat/unread_count')
@login_required
def unread_count_api():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM messages WHERE recipient_id = ? AND is_read = 0",
        (session['user_id'],),
    )
    count = c.fetchone()[0]
    conn.close()
    return {'count': count}


@app.route('/my/chat')
@login_required
def my_chat():
    if session.get('is_admin'):
        return redirect(url_for('admin_chat_index'))
    user_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT u.id, u.name FROM users u
        INNER JOIN admin_managed_users m ON u.id = m.admin_id
        WHERE m.user_id = ? ORDER BY u.name
        """,
        (user_id,),
    )
    admins = c.fetchall()
    conn.close()
    if not admins:
        return 'チャット可能な管理者が設定されていません'
    return render_template('chat_list.html', users=admins, as_admin=False)


@app.route('/admin/chat')
@admin_required
def admin_chat_index():
    admin_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT u.id, u.name FROM users u
        INNER JOIN admin_managed_users m ON u.id = m.user_id
        WHERE m.admin_id = ? ORDER BY u.name
        """,
        (admin_id,),
    )
    users = c.fetchall()
    conn.close()
    return render_template('chat_list.html', users=users, as_admin=True)


@app.route('/admin/chat/<int:user_id>')
@admin_required
def admin_chat(user_id):
    if not can_chat(session['user_id'], user_id):
        return 'アクセス拒否'
    return redirect(url_for('chat', partner_id=user_id))

@app.route('/admin/export', methods=['GET', 'POST'])
@admin_required
def export_combined():
    admin_id = session['user_id']
    conn = get_db()
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
        delete_old_exports(EXPORT_DIR)
        if not check_csrf():
            return redirect(url_for('export_combined'))
        year = int(request.form['year'])
        month = int(request.form['month'])
        if request.form['action'] == 'single_user':
            user_id = int(request.form['user_id'])
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT name FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            conn.close()
            if not row:
                return 'ユーザーが見つかりません'
            name = row['name']
            export_subdir = os.path.join(EXPORT_DIR, f"{year}", f"{month:02d}")
            os.makedirs(export_subdir, exist_ok=True)
            csv_path = generate_csv(user_id, name, year, month, export_subdir, fetch_overtime_threshold(user_id))
            if not csv_path:
                flash('該当データがありません。', 'warning')
                return redirect(url_for('export_combined'))
            return send_file(csv_path, mimetype='text/csv', as_attachment=True, download_name=os.path.basename(csv_path))
        elif request.form['action'] == 'bulk_all':
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, f"勤怠記録_{year}_{month:02d}.zip")
                any_file = False
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for user_id, name in user_list:
                        csv_file = generate_csv(user_id, name, year, month, temp_dir, fetch_overtime_threshold(user_id))
                        if csv_file:
                            zipf.write(csv_file, os.path.basename(csv_file))
                            any_file = True
                if not any_file:
                    flash('該当データがありません。', 'warning')
                    return redirect(url_for('export_combined'))
                return send_file(zip_path, mimetype='application/zip', as_attachment=True, download_name=f"勤怠記録_{year}_{month:02d}.zip")
    return render_template('export.html', user_list=user_list, now=now, years=years)

@app.route('/admin/users')
@admin_required
def list_users():
    admin_id = session['user_id']
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, email, is_admin, is_superadmin FROM users ORDER BY name")
    all_users = c.fetchall()
    c.execute("SELECT user_id FROM admin_managed_users WHERE admin_id = ?", (admin_id,))
    managed_ids = {row['user_id'] for row in c.fetchall()}
    conn.close()
    users = []
    for user in all_users:
        users.append({
            'id_name': user,
            'is_managed': user['id'] in managed_ids
        })
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    errors = {}
    if request.method == 'POST':
        if not check_csrf():
            return redirect(url_for('create_user'))
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        is_admin = int('is_admin' in request.form)

        if not name:
            errors['name'] = "氏名を入力してください。"
        if not is_valid_email(email):
            errors['email'] = "正しいメールアドレスを入力してください。"
        if not password or len(password) < 8:
            errors['password'] = "パスワードは8文字以上で入力してください。"
        if not confirm:
            errors['confirm_password'] = "パスワード（確認）を入力してください。"
        elif password and password != confirm:
            errors['confirm_password'] = "パスワードが一致しません。"

        if errors:
            return render_template('create_user.html', errors=errors)

        password_hash = generate_password_hash(password)
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (name, email, password_hash, is_admin, is_superadmin) VALUES (?, ?, ?, ?, 0)",
                      (name, email, password_hash, is_admin))
            conn.commit()
            send_registration_email(email, name)
        except sqlite3.IntegrityError:
            conn.close()
            errors['email'] = "このメールアドレスはすでに登録されています。"
            return render_template('create_user.html', errors=errors)
        conn.close()
        flash("ユーザーを作成しました。", "success")
        return redirect_embedded('list_users')
    return render_template('create_user.html', errors=errors)

@app.route('/admin/users/manage', methods=['POST'])
@admin_required
def update_managed_users():
    if not check_csrf():
        return redirect_embedded('list_users')
    admin_id = session['user_id']
    selected_ids = request.form.getlist('managed_users')
    selected_ids = list(map(int, selected_ids))
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM admin_managed_users WHERE admin_id = ?", (admin_id,))
    for user_id in selected_ids:
        c.execute("INSERT INTO admin_managed_users (admin_id, user_id) VALUES (?, ?)", (admin_id, user_id))
    conn.commit()
    conn.close()
    flash("管理対象を更新しました。", "success")
    return redirect_embedded('list_users')

@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, email, is_admin, overtime_threshold, is_superadmin FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        flash("ユーザーが見つかりません。", "danger")
        return redirect_embedded('list_users')

    errors = {}
    if request.method == 'POST':
        if not check_csrf():
            return redirect_embedded('edit_user', user_id=user_id)
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        is_admin = 1 if user['is_superadmin'] else int('is_admin' in request.form)
        overtime_threshold = request.form.get('overtime_threshold', '18:00').strip()
        new_password = request.form.get('new_password', '').strip()

        if not name:
            errors['name'] = "氏名を入力してください。"
        if not is_valid_email(email):
            errors['email'] = "正しいメールアドレスを入力してください。"
        if overtime_threshold and not is_valid_time(overtime_threshold):
            errors['overtime_threshold'] = "残業カウント開始時刻は HH:MM 形式で入力してください。"
        # パスワードは空欄でもOK。入っている場合のみ長さバリデーション
        if new_password and len(new_password) < 8:
            errors['new_password'] = "パスワードは8文字以上で入力してください。"

        if errors:
            conn.close()
            return render_template('edit_user.html', user_id=user_id, user=user, errors=errors)

        try:
            c.execute("UPDATE users SET name = ?, email = ?, is_admin = ?, overtime_threshold = ? WHERE id = ?",
                      (name, email, is_admin, overtime_threshold, user_id))
            if new_password:
                password_hash = generate_password_hash(new_password)
                c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
                flash("パスワードを更新しました。", "success")
            conn.commit()
            flash("ユーザー情報を更新しました。", "success")
        except sqlite3.IntegrityError:
            errors['email'] = "このメールアドレスは既に登録されています。"
            conn.close()
            return render_template('edit_user.html', user_id=user_id, user=user, errors=errors)
        conn.close()
        return redirect_embedded('list_users')

    conn.close()
    return render_template('edit_user.html', user_id=user_id, user=user, errors=errors)

@app.route('/admin/users/delete/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def delete_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, is_superadmin FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        flash("ユーザーが見つかりません。", "danger")
        return redirect_embedded('list_users')

    if request.method == 'POST':
        if not check_csrf():
            conn.close()
            return redirect_embedded('list_users')
        if user_id == session.get('user_id'):
            flash("自分自身のアカウントは削除できません。", "danger")
            conn.close()
            return redirect_embedded('list_users')
        if user['is_superadmin']:
            flash("スーパー管理者は削除できません。", "danger")
            conn.close()
            return redirect_embedded('list_users')
        c.execute(
            "DELETE FROM messages WHERE sender_id = ? OR recipient_id = ?",
            (user_id, user_id),
        )
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash("ユーザーを削除しました。", "success")
        return redirect_embedded('list_users')

    conn.close()
    return render_template('confirm_delete_user.html', user=user)


@app.route('/admin/mail_settings', methods=['GET', 'POST'])
@superadmin_required
def mail_settings():
    errors = {}
    settings = get_mail_settings() or {}
    if request.method == 'POST':
        if not check_csrf():
            return redirect_embedded('mail_settings')
        server = request.form.get('server', '').strip()
        port = request.form.get('port', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        use_tls = int('use_tls' in request.form)
        subject_tmpl = request.form.get('subject_template', '').strip()
        body_tmpl = request.form.get('body_template', '').strip()
        if not server:
            errors['server'] = 'サーバーを入力してください。'
        if not port.isdigit():
            errors['port'] = 'ポート番号を入力してください。'
        if errors:
            settings.update(request.form)
            return render_template('mail_settings.html', settings=settings, errors=errors)
        save_mail_settings(server, int(port), username, password, use_tls, subject_tmpl, body_tmpl)
        flash('メール設定を更新しました。', 'success')
        return redirect_embedded('mail_settings')
    return render_template('mail_settings.html', settings=settings, errors=errors)


@app.route('/admin/audit_log')
@superadmin_required
def view_audit_log():
    if os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    else:
        lines = []
    lines = list(reversed(lines[-500:]))
    log_text = ''.join(lines)
    return render_template('audit_log.html', log_text=log_text)


@app.route('/admin/audit_log/download')
@superadmin_required
def download_audit_log():
    if not os.path.exists(AUDIT_LOG_PATH):
        return '監査ログがありません', 404
    return send_file(
        AUDIT_LOG_PATH,
        as_attachment=True,
        mimetype='text/plain',
        download_name=os.path.basename(AUDIT_LOG_PATH)
    )


@app.route('/admin/update', methods=['GET', 'POST'])
@superadmin_required
def update_system():
    local, remote = get_git_commits()
    error = None
    update_available = False
    critical_changes = False
    changed_files = []
    if local is None:
        error = 'Gitリポジトリではありません。'
    elif remote is None:
        error = 'リモートリポジトリが設定されていません。'
    else:
        update_available = local != remote
        if update_available:
            files = get_changed_files() or []
            changed_files = files
            for f in files:
                if f.startswith('database/') or f == '.env.example':
                    critical_changes = True
                    break
    if request.method == 'POST':
        if not check_csrf():
            return redirect_embedded('update_system')
        if critical_changes:
            flash('重要なファイルが変更されているため自動アップデートできません。', 'danger')
            return render_template(
                'update.html',
                local_commit=local,
                remote_commit=remote,
                update_available=True,
                critical_changes=True,
                changed_files=changed_files,
                error=None,
            )
        message = perform_git_pull()
        flash('アップデートを実行しました。サーバーを再起動してください。', 'success')
        return render_template(
            'update.html',
            local_commit=local,
            remote_commit=remote,
            update_available=False,
            error=None,
            message=message,
        )
    return render_template(
        'update.html',
        local_commit=local,
        remote_commit=remote,
        update_available=update_available,
        critical_changes=critical_changes,
        changed_files=changed_files,
        error=error,
    )

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    if count > 0:
        conn.close()
        return redirect(url_for('login'))
    if request.method == 'POST':
        if not check_csrf():
            return redirect(url_for('setup'))
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm = request.form.get('confirm_password', '')
        errors = []
        if not name:
            errors.append("氏名を入力してください。")
        if not is_valid_email(email):
            errors.append("正しいメールアドレスを入力してください。")
        if not password or len(password) < 8:
            errors.append("パスワードは8文字以上で入力してください。")
        if not confirm:
            errors.append("パスワード（確認）を入力してください。")
        elif password != confirm:
            errors.append("パスワードが一致しません。")
        if errors:
            for msg in errors:
                flash(msg, "danger")
            conn.close()
            return redirect(url_for('setup'))
        password_hash = generate_password_hash(password)
        c.execute("INSERT INTO users (email, name, password_hash, is_admin, is_superadmin) VALUES (?, ?, ?, 1, 1)",(email, name, password_hash))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    conn.close()
    return render_template('setup.html')

if __name__ == '__main__':
    debug_env = os.environ.get('FLASK_DEBUG', '0')
    debug_mode = str(debug_env).lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=8000, debug=debug_mode)
