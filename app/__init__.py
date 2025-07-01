try:
    from gevent import monkey
    monkey.patch_all()
except ImportError:
    pass

from flask import Flask, g, request
from datetime import timedelta
import os
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import time
import secrets
from dotenv import load_dotenv

load_dotenv()

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
    
    # リクエスト処理
    setup_request_handlers(app)
    
    # Jinja2環境の設定
    setup_jinja2(app)
    
    # Blueprintの登録
    from app.auth import auth_bp
    from app.attendance import attendance_bp
    from app.chat import chat_bp
    from app.admin import admin_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(attendance_bp)
    app.register_blueprint(chat_bp, url_prefix='/chat')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
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
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'kintai.db')
    app.config['DB_PATH'] = DB_PATH
    
    def get_db():
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect(DB_PATH, timeout=10)
            db.row_factory = sqlite3.Row
        return db
    
    def close_db(error):
        db = getattr(g, '_database', None)
        if db is not None:
            db.close()
    
    app.teardown_appcontext(close_db)
    app.get_db = get_db

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