from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import check_password_hash
from functools import wraps
import secrets
import os
from ..models import User
from ..utils.validators import is_valid_email
from ..utils.audit import log_audit_event

auth_bp = Blueprint('auth', __name__)

def check_csrf():
    """CSRF トークンの検証"""
    token = request.form.get('_csrf_token')
    if token and session.get('_csrf_token'):
        return secrets.compare_digest(token, session['_csrf_token'])
    return False

def login_required(f):
    """ログイン必須デコレーター"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """管理者権限必須デコレーター"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if not session.get('is_admin') and not session.get('is_superadmin'):
            flash("管理者権限が必要です", "danger")
            return redirect(url_for('attendance.index')), 403
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    """スーパー管理者権限必須デコレーター"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if not session.get('is_superadmin'):
            flash("スーパー管理者権限が必要です", "danger")
            return redirect(url_for('attendance.index')), 403
        return f(*args, **kwargs)
    return decorated_function

@auth_bp.before_app_request
def load_user():
    """ユーザー情報をリクエストコンテキストに読み込み"""
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        try:
            g.user = User.get_by_id(user_id)
        except Exception:
            g.user = None

@auth_bp.before_app_request
def check_setup():
    """初期セットアップのチェック"""
    if request.endpoint and request.endpoint.startswith('auth.setup'):
        return
    
    # 初回起動時のセットアップチェック
    try:
        users = User.get_all()
        if not users:
            return redirect(url_for('auth.setup'))
    except Exception:
        # データベースが未初期化の場合はセットアップへリダイレクトしない
        return

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """ログイン"""
    if request.method == 'POST':
        if not check_csrf():
            flash("不正なリクエストです", "danger")
            return redirect(url_for('auth.login'))
        
        email = request.form['email'].strip().lower()
        password = request.form['password']
        
        if not email or not password:
            flash("メールアドレスとパスワードを入力してください", "danger")
            return render_template('login.html')
        
        user = User.get_by_email(email)
        
        if user and check_password_hash(user['password_hash'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['is_admin'] = bool(user['is_admin'])
            session['is_superadmin'] = bool(user['is_superadmin'])
            
            log_audit_event("login", user['id'], user['name'])
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('attendance.index'))
        else:
            flash("メールアドレスまたはパスワードが間違っています", "danger")
            log_audit_event("login_failed", None, email)
    
    # CSRFトークンを生成
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """ログアウト"""
    user_name = session.get('user_name', '')
    user_id = session.get('user_id')
    
    log_audit_event("logout", user_id, user_name)
    
    session.clear()
    flash("ログアウトしました", "info")
    return redirect(url_for('auth.login'))

@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """初期セットアップ"""
    if request.method == 'POST':
        admin_email = request.form['admin_email'].strip().lower()
        admin_name = request.form['admin_name'].strip()
        admin_password = request.form['admin_password']
        
        # バリデーション
        if not admin_email or not admin_name or not admin_password:
            flash("すべての項目を入力してください", "danger")
            return render_template('setup.html')
        
        if not is_valid_email(admin_email):
            flash("有効なメールアドレスを入力してください", "danger")
            return render_template('setup.html')
        
        if len(admin_password) < 8:
            flash("パスワードは8文字以上で入力してください", "danger")
            return render_template('setup.html')
        
        try:
            # スーパー管理者を作成
            User.create(
                email=admin_email,
                name=admin_name,
                password=admin_password,
                is_admin=True,
                is_superadmin=True
            )
            
            log_audit_event("system_setup", None, admin_name)
            flash("初期セットアップが完了しました", "success")
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            flash(f"セットアップに失敗しました: {str(e)}", "danger")
    
    return render_template('setup.html')

@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """パスワード変更"""
    if request.method == 'POST':
        if not check_csrf():
            flash("不正なリクエストです", "danger")
            return redirect(url_for('auth.change_password'))
        
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # バリデーション
        if not current_password or not new_password or not confirm_password:
            flash("すべての項目を入力してください", "danger")
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash("新しいパスワードが一致しません", "danger")
            return render_template('change_password.html')
        
        if len(new_password) < 8:
            flash("パスワードは8文字以上で入力してください", "danger")
            return render_template('change_password.html')
        
        # 現在のパスワード確認
        user = User.get_by_id(session['user_id'])
        if not user or not check_password_hash(user['password_hash'], current_password):
            flash("現在のパスワードが間違っています", "danger")
            return render_template('change_password.html')
        
        # パスワード更新
        User.update_password(session['user_id'], new_password)
        
        log_audit_event("password_change", session['user_id'], session['user_name'])
        flash("パスワードを変更しました", "success")
        return redirect(url_for('auth.my_page'))
    
    # CSRFトークンを生成
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    
    return render_template('change_password.html')

@auth_bp.route('/my_page')
@login_required
def my_page():
    """マイページ"""
    return render_template('my_page.html')