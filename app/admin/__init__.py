from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from datetime import datetime
import os
import tempfile
import zipfile
import subprocess
import json
from ..auth import admin_required, superadmin_required, check_csrf
from ..models import User, MailSettings, AdminManagedUsers
from ..utils.validators import is_valid_email
from ..utils.audit import log_audit_event
from ..utils.csv_helpers import generate_csv
from ..utils.file_helpers import sanitize_filename, delete_old_exports
from ..utils.email_helpers import send_email, send_registration_email
from ..utils.git_helpers import get_git_commits, update_system

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """管理者ダッシュボード"""
    # Git コミット情報を取得
    commits = get_git_commits()
    
    # システム情報
    system_info = {
        'commits': commits,
        'has_updates': len(commits.get('behind', [])) > 0 if commits else False
    }
    
    return render_template('admin_dashboard.html', system_info=system_info)

@admin_bp.route('/users')
@admin_required
def users():
    """ユーザー管理"""
    all_users = User.get_all()
    admin_id = session['user_id']
    
    # 現在の管理対象ユーザーを取得
    managed_users = User.get_managed_users(admin_id)
    managed_user_ids = {user[0] for user in managed_users}
    # 管理者もスーパー管理者も全ユーザーを表示
    
    return render_template('admin_users.html', users=all_users, managed_user_ids=managed_user_ids)

@admin_bp.route('/create_user', methods=['GET', 'POST'])
@admin_required
def create_user():
    """ユーザー作成"""
    if request.method == 'POST':
        if not check_csrf():
            flash("不正なリクエストです", "danger")
            return redirect(url_for('admin.create_user'))
        
        email = request.form['email'].strip().lower()
        name = request.form['name'].strip()
        password = request.form['password']
        is_admin = 'is_admin' in request.form
        is_superadmin = 'is_superadmin' in request.form and session.get('is_superadmin')
        overtime_threshold = request.form.get('overtime_threshold', '18:00')
        
        # バリデーション
        if not email or not name or not password:
            flash("すべての項目を入力してください", "danger")
            return render_template('create_user.html')
        
        if not is_valid_email(email):
            flash("有効なメールアドレスを入力してください", "danger")
            return render_template('create_user.html')
        
        if len(password) < 8:
            flash("パスワードは8文字以上で入力してください", "danger")
            return render_template('create_user.html')
        
        if len(name) > 100:
            flash("名前は100文字以内で入力してください", "danger")
            return render_template('create_user.html')
        
        # 重複チェック
        if User.get_by_email(email):
            flash("このメールアドレスは既に登録されています", "danger")
            return render_template('create_user.html')
        
        try:
            # ユーザー作成
            user_id = User.create(email, name, password, is_admin, is_superadmin, overtime_threshold)

            # 一般管理者が作成した場合、自動的に管理対象に追加
            if not session.get('is_superadmin'):
                AdminManagedUsers.add_managed_user(session['user_id'], user_id)

            # 登録通知メールを送信（失敗しても処理続行）
            try:
                send_registration_email(email, name)
            except Exception:
                pass
            
            log_audit_event("user_created", session['user_id'], f"Created user: {name}")
            flash("ユーザーを作成しました", "success")
            return redirect(url_for('admin.users'))
            
        except Exception as e:
            flash("ユーザーの作成に失敗しました", "danger")
    
    return render_template('create_user.html')

@admin_bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """ユーザー編集"""
    user = User.get_by_id(user_id)
    if not user:
        flash("ユーザーが見つかりません", "danger")
        return redirect(url_for('admin.users'))
    
    # アクセス権限チェック
    if not session.get('is_superadmin'):
        admin_id = session['user_id']
        if user_id != admin_id and not AdminManagedUsers.is_managed_by(admin_id, user_id):
            flash("このユーザーを編集する権限がありません", "danger")
            return redirect(url_for('admin.users'))
    
    if request.method == 'POST':
        if not check_csrf():
            flash("不正なリクエストです", "danger")
            return redirect(url_for('admin.edit_user', user_id=user_id))
        
        email = request.form['email'].strip().lower()
        name = request.form['name'].strip()
        is_admin = 'is_admin' in request.form
        is_superadmin = 'is_superadmin' in request.form and session.get('is_superadmin')
        overtime_threshold = request.form.get('overtime_threshold', '18:00')
        
        # バリデーション
        if not email or not name:
            flash("メールアドレスと名前を入力してください", "danger")
            return render_template('edit_user.html', user=user)
        
        if not is_valid_email(email):
            flash("有効なメールアドレスを入力してください", "danger")
            return render_template('edit_user.html', user=user)
        
        if len(name) > 100:
            flash("名前は100文字以内で入力してください", "danger")
            return render_template('edit_user.html', user=user)
        
        # 重複チェック（自分以外）
        existing_user = User.get_by_email(email)
        if existing_user and existing_user['id'] != user_id:
            flash("このメールアドレスは既に登録されています", "danger")
            return render_template('edit_user.html', user=user)
        
        try:
            User.update(user_id, email, name, is_admin, is_superadmin, overtime_threshold)
            
            log_audit_event("user_updated", session['user_id'], f"Updated user: {name}")
            flash("ユーザー情報を更新しました", "success")
            return redirect(url_for('admin.users'))
            
        except Exception as e:
            flash("ユーザー情報の更新に失敗しました", "danger")
    
    return render_template('edit_user.html', user=user)

@admin_bp.route('/delete_user/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def delete_user(user_id):
    """ユーザー削除"""
    user = User.get_by_id(user_id)
    if not user:
        flash("ユーザーが見つかりません", "danger")
        return redirect(url_for('admin.users'))
    
    # 自分自身は削除できない
    if user_id == session['user_id']:
        flash("自分自身を削除することはできません", "danger")
        return redirect(url_for('admin.users'))
    
    # アクセス権限チェック
    if not session.get('is_superadmin'):
        admin_id = session['user_id']
        if not AdminManagedUsers.is_managed_by(admin_id, user_id):
            flash("このユーザーを削除する権限がありません", "danger")
            return redirect(url_for('admin.users'))
    
    if request.method == 'POST':
        if not check_csrf():
            flash("不正なリクエストです", "danger")
            return redirect(url_for('admin.delete_user', user_id=user_id))
        
        try:
            User.delete(user_id)
            
            log_audit_event("user_deleted", session['user_id'], f"Deleted user: {user['name']}")
            flash("ユーザーを削除しました", "success")
            
        except Exception as e:
            flash("ユーザーの削除に失敗しました", "danger")
        
        return redirect(url_for('admin.users'))
    
    return render_template('confirm_delete_user.html', user=user)

@admin_bp.route('/update_managed_users', methods=['POST'])
@admin_required
def update_managed_users():
    """管理対象ユーザーを更新"""
    if not check_csrf():
        flash("不正なリクエストです", "danger")
        return redirect(url_for('admin.users'))
    
    managed_users = request.form.getlist('managed_users')
    admin_id = session['user_id']
    
    try:
        # 現在の管理対象ユーザーを取得
        current_managed = User.get_managed_users(admin_id)
        current_managed_ids = {user[0] for user in current_managed}
        
        # 新しい管理対象ユーザーIDのセット
        new_managed_ids = {int(user_id) for user_id in managed_users}
        
        # 削除すべきユーザー
        to_remove = current_managed_ids - new_managed_ids
        
        # 追加すべきユーザー
        to_add = new_managed_ids - current_managed_ids
        
        # 削除処理
        for user_id in to_remove:
            AdminManagedUsers.remove_managed_user(admin_id, user_id)
        
        # 追加処理
        for user_id in to_add:
            AdminManagedUsers.add_managed_user(admin_id, user_id)
        
        flash(f"{len(managed_users)}人のユーザーを管理対象として設定しました", "success")
        
        log_audit_event("managed_users_updated", session['user_id'], session['user_name'])
        
    except Exception as e:
        flash("管理対象ユーザーの更新に失敗しました", "danger")
    
    # embeddedモードかどうかを確認してリダイレクト先を調整
    if request.form.get('embedded'):
        return redirect(url_for('admin.users', embedded=1))
    else:
        return redirect(url_for('admin.users'))

@admin_bp.route('/export', methods=['GET', 'POST'])
@admin_required
def export():
    """CSV エクスポート"""
    if request.method == 'POST':
        if not check_csrf():
            flash("不正なリクエストです", "danger")
            return redirect(url_for('admin.export'))
        
        export_type = request.form['export_type']
        year = int(request.form['year'])
        month = int(request.form['month'])
        
        # バリデーション
        current_year = datetime.now().year
        if not (2020 <= year <= current_year + 1):
            flash("有効な年を選択してください", "danger")
            return render_template('export.html')
        
        if not (1 <= month <= 12):
            flash("有効な月を選択してください", "danger")
            return render_template('export.html')
        
        try:
            if export_type == 'single_user':
                # 単一ユーザーエクスポート
                user_id = int(request.form['user_id'])
                user = User.get_by_id(user_id)
                
                if not user:
                    flash("ユーザーが見つかりません", "danger")
                    return render_template('export.html')
                
                # アクセス権限チェック
                if not session.get('is_superadmin'):
                    admin_id = session['user_id']
                    if user_id != admin_id and not AdminManagedUsers.is_managed_by(admin_id, user_id):
                        flash("このユーザーのデータをエクスポートする権限がありません", "danger")
                        return render_template('export.html')
                
                overtime_threshold = User.get_overtime_threshold(user_id)
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    csv_file = generate_csv(user_id, user['name'], year, month, temp_dir, overtime_threshold)
                    
                    if csv_file and os.path.exists(csv_file):
                        log_audit_event("admin_export_single", session['user_id'], f"Exported {user['name']} {year}/{month}")
                        
                        filename = f"{sanitize_filename(user['name'])}_{year}_{month:02d}_勤怠記録.csv"
                        return send_file(csv_file, as_attachment=True, download_name=filename)
                    else:
                        flash("CSVファイルの生成に失敗しました", "danger")
            
            elif export_type == 'bulk_all':
                # 一括エクスポート
                admin_id = session['user_id']
                
                if session.get('is_superadmin'):
                    # スーパー管理者は全ユーザー
                    user_list = [(user['id'], user['name']) for user in User.get_all()]
                else:
                    # 一般管理者は管理対象ユーザーのみ
                    user_list = [(user['id'], user['name']) for user in User.get_managed_users(admin_id)]
                
                if not user_list:
                    flash("エクスポート対象のユーザーがありません", "danger")
                    return render_template('export.html')
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_filename = f"勤怠記録_{year}_{month:02d}_一括.zip"
                    zip_path = os.path.join(temp_dir, zip_filename)
                    
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for user_id, name in user_list:
                            overtime_threshold = User.get_overtime_threshold(user_id)
                            csv_file = generate_csv(user_id, name, year, month, temp_dir, overtime_threshold)
                            
                            if csv_file and os.path.exists(csv_file):
                                arcname = f"{sanitize_filename(name)}_{year}_{month:02d}_勤怠記録.csv"
                                zipf.write(csv_file, arcname)
                    
                    if os.path.exists(zip_path):
                        log_audit_event("admin_export_bulk", session['user_id'], f"Bulk export {year}/{month}")
                        return send_file(zip_path, as_attachment=True, download_name=zip_filename)
                    else:
                        flash("ZIPファイルの生成に失敗しました", "danger")
                        
        except Exception as e:
            flash("エクスポートに失敗しました", "danger")
    
    # 全ユーザー一覧を取得（管理者もスーパー管理者も全ユーザーを表示）
    try:
        users = User.get_all()
        user_list = [(u['id'], u['name']) for u in users]
        from datetime import datetime
        now = datetime.now()
        # 年の選択肢を生成（過去5年から来年まで）
        years = list(range(now.year - 5, now.year + 2))
        return render_template('export.html', user_list=user_list, now=now, years=years)
    except Exception as e:
        print(f"Export page error: {e}")
        import traceback
        traceback.print_exc()
        flash("ユーザー一覧の取得に失敗しました", "danger")
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/mail_settings', methods=['GET', 'POST'])
@superadmin_required
def mail_settings():
    """メール設定"""
    if request.method == 'POST':
        if not check_csrf():
            flash("不正なリクエストです", "danger")
            return redirect(url_for('admin.mail_settings'))
        
        server = request.form['server'].strip()
        port = request.form['port']
        username = request.form['username'].strip()
        password = request.form['password']
        use_tls = 'use_tls' in request.form
        subject_template = request.form['subject_template'].strip()
        body_template = request.form['body_template'].strip()
        
        # バリデーション
        errors = []
        if not server or not port:
            errors.append("サーバーとポートは必須です")
        
        try:
            port = int(port)
            if not (1 <= port <= 65535):
                raise ValueError()
        except ValueError:
            errors.append("有効なポート番号を入力してください")
        
        if errors:
            for error in errors:
                flash(error, "danger")
            settings_row = MailSettings.get()
            
            # タプルを辞書に変換
            if settings_row:
                settings = {
                    'server': settings_row[0],
                    'port': settings_row[1],
                    'username': settings_row[2],
                    'password': settings_row[3],
                    'use_tls': settings_row[4],
                    'subject_template': settings_row[5],
                    'body_template': settings_row[6]
                }
            else:
                settings = {
                    'server': '',
                    'port': 587,
                    'username': '',
                    'password': '',
                    'use_tls': True,
                    'subject_template': '',
                    'body_template': ''
                }
            return render_template('mail_settings.html', settings=settings, errors={})
        
        try:
            MailSettings.update(server, port, username, password, use_tls, subject_template, body_template)
            
            log_audit_event("mail_settings_updated", session['user_id'], session['user_name'])
            flash("メール設定を更新しました", "success")
            
        except Exception as e:
            flash("メール設定の更新に失敗しました", "danger")
    
    # 現在の設定を取得
    settings_row = MailSettings.get()
    
    # タプルを辞書に変換（SQLiteのfetchone()結果を辞書形式に）
    if settings_row:
        settings = {
            'server': settings_row[0],
            'port': settings_row[1],
            'username': settings_row[2],
            'password': settings_row[3],
            'use_tls': settings_row[4],
            'subject_template': settings_row[5],
            'body_template': settings_row[6]
        }
    else:
        settings = {
            'server': '',
            'port': 587,
            'username': '',
            'password': '',
            'use_tls': True,
            'subject_template': '',
            'body_template': ''
        }
    
    return render_template('mail_settings.html', settings=settings, errors={})

@admin_bp.route('/audit_log')
@superadmin_required
def audit_log():
    """監査ログ表示"""
    audit_log_path = os.environ.get('AUDIT_LOG_PATH', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs', 'audit.log'))
    
    lines = []
    if os.path.exists(audit_log_path):
        try:
            with open(audit_log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            lines = []
    
    # 最新500行を表示
    lines = list(reversed(lines[-500:]))
    
    return render_template('audit_log.html', log_lines=lines)

@admin_bp.route('/download_audit_log')
@superadmin_required
def download_audit_log():
    """監査ログダウンロード"""
    audit_log_path = os.environ.get('AUDIT_LOG_PATH', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs', 'audit.log'))
    
    if os.path.exists(audit_log_path):
        log_audit_event("audit_log_downloaded", session['user_id'], session['user_name'])
        return send_file(audit_log_path, as_attachment=True, download_name='audit.log')
    else:
        flash("監査ログファイルが見つかりません", "warning")
        return redirect(url_for('admin.audit_log'))

@admin_bp.route('/update_system', methods=['GET', 'POST'])
@superadmin_required
def update_system_page():
    """システム更新画面・実行"""
    if request.method == 'POST':
        if not check_csrf():
            flash("不正なリクエストです", "danger")
            return redirect(url_for('admin.update_system_page'))
        
        try:
            result = update_system()
            
            if result['success']:
                log_audit_event("system_updated", session['user_id'], session['user_name'])
                flash("システムを更新しました", "success")
            else:
                flash(f"システム更新に失敗しました: {result['error']}", "danger")
                
        except Exception as e:
            flash("システム更新中にエラーが発生しました", "danger")
        
        return redirect(url_for('admin.update_system_page'))
    
    # GET request
    # Git コミット情報を取得
    commits = get_git_commits()
    
    # システム情報
    system_info = {
        'commits': commits,
        'has_updates': len(commits.get('behind', [])) > 0 if commits else False
    }
    
    return render_template('update.html', system_info=system_info)