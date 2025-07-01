try:
    from gevent import monkey
    monkey.patch_all()
except ImportError:
    pass

from flask import Flask, g, request, send_file
from datetime import timedelta
import os
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import time
import secrets
from dotenv import load_dotenv

load_dotenv()

# デフォルトのデータベースパス
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'kintai.db')
EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'exports')

def create_app(config=None):
    """アプリケーションファクトリ"""
    # テンプレートとstaticフォルダのパスを設定
    import os
    base_dir = os.path.dirname(os.path.dirname(__file__))
    template_folder = os.path.join(base_dir, 'templates')
    static_folder = os.path.join(base_dir, 'static')
    
    app = Flask(__name__, 
                template_folder=template_folder,
                static_folder=static_folder)
    
    # 設定の読み込み
    app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key_here')
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 10 * 1024 * 1024))
    app.permanent_session_lifetime = timedelta(
        days=int(os.environ.get('SESSION_LIFETIME_DAYS', 7))
    )
    
    if not app.secret_key or app.secret_key == 'your_secret_key_here':
        raise RuntimeError("SECRET_KEYを環境変数で必ず設定してください")
    
    # ログ設定
    setup_logging(app)
    
    # データベース設定
    setup_database(app)

    # エクスポートディレクトリ設定
    os.makedirs(EXPORT_DIR, exist_ok=True)
    app.config['EXPORT_DIR'] = EXPORT_DIR
    
    # リクエスト処理
    setup_request_handlers(app)
    register_error_handlers(app)
    
    # Jinja2環境の設定
    setup_jinja2(app)
    
    # Blueprintの登録
    from app.auth import auth_bp, admin_required
    from app.attendance import attendance_bp
    from app.chat import chat_bp
    from app.admin import admin_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(attendance_bp)
    app.register_blueprint(chat_bp, url_prefix='/chat')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    @app.route('/exports/<path:filename>')
    @admin_required
    def download_export_file(filename):
        """エクスポートファイルを安全に配布"""
        export_root = os.path.realpath(app.config['EXPORT_DIR'])
        filepath = os.path.realpath(os.path.join(export_root, filename))
        if not filepath.startswith(export_root + os.sep):
            return '不正なファイルパスです', 400
        if os.path.islink(os.path.join(export_root, filename)):
            return '不正なファイルパスです', 400
        if not os.path.isfile(filepath):
            return 'ファイルが存在しません', 404
        return send_file(filepath, as_attachment=True, mimetype='text/csv')
    
    # コンテキストプロセッサーの設定
    setup_context_processors(app)
    
    # ルートURLの設定
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('attendance.index'))
    
    return app

def setup_logging(app):
    """ログ設定"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'app.log')
    
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(__name__)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def setup_database(app):
    """データベース設定"""
    app.config['DB_PATH'] = DB_PATH
    
    def get_db():
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect(app.config['DB_PATH'], timeout=10)
            db.row_factory = sqlite3.Row
        return db
    
    def close_db(error):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()
    
    app.teardown_appcontext(close_db)
    app.get_db = get_db


def initialize_database(db_path: str | None = None):
    """データベースを初期化"""
    global DB_PATH, EXPORT_DIR
    path = db_path or DB_PATH
    DB_PATH = path
    app.config['DB_PATH'] = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    app.config['EXPORT_DIR'] = EXPORT_DIR
    schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'schema.sql')
    conn = sqlite3.connect(path)
    with open(schema_path, encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

def setup_request_handlers(app):
    """リクエストハンドラー設定"""
    @app.before_request
    def log_request_start():
        g.start_time = time.time()
        logger = logging.getLogger(__name__)
        logger.info(f"Request start: {request.method} {request.path} from {request.remote_addr}")

    @app.after_request
    def log_request_end(response):
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            logger = logging.getLogger(__name__)
            logger.info(
                f"Request end: {request.method} {request.path} - Status: {response.status_code} - Duration: {duration:.4f}s"
            )
        return response


def register_error_handlers(app):
    """アプリケーションのエラーハンドラーを登録"""
    from werkzeug.exceptions import RequestEntityTooLarge

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(e):
        return "File too large", 413

def setup_jinja2(app):
    """Jinja2環境の設定"""
    @app.template_global()
    def csrf_token():
        """CSRFトークンを生成してテンプレートで使用可能にする"""
        from flask import session
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(16)
        return session['_csrf_token']

def setup_context_processors(app):
    """コンテキストプロセッサー設定"""
    from flask import session
    
    @app.context_processor
    def inject_unread_count():
        if 'user_id' not in session:
            return {'unread_count': 0}
        
        db = app.get_db()
        c = db.cursor()
        c.execute(
            "SELECT COUNT(*) FROM messages WHERE recipient_id = ? AND is_read = 0",
            (session['user_id'],),
        )
        result = c.fetchone()
        return {'unread_count': result[0] if result else 0}


# 互換性のためのグローバルオブジェクトと関数を公開
app = create_app()

# テスト用に関数を公開
# (旧API互換のためにモジュールレベルで公開)

from .auth import check_csrf, login_required, admin_required, superadmin_required
from .utils.validators import is_valid_email, is_valid_time
from .utils.datetime_helpers import calculate_overtime
from .utils.csv_helpers import generate_csv

__all__ = [
    "app",
    "create_app",
    "initialize_database",
    "check_csrf",
    "login_required",
    "admin_required",
    "superadmin_required",
    "is_valid_email",
    "is_valid_time",
    "calculate_overtime",
    "generate_csv",
    "DB_PATH",
    "EXPORT_DIR",
]
