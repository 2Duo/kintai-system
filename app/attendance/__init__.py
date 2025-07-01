from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file
from datetime import datetime, timedelta
import csv
import os
import tempfile
from collections import defaultdict
from io import TextIOWrapper
from ..auth import login_required, check_csrf
from ..models import User, Attendance
from ..utils.validators import is_valid_time
from ..utils.datetime_helpers import safe_fromisoformat, normalize_time_str, calculate_overtime
from ..utils.audit import log_audit_event
from ..utils.csv_helpers import generate_csv
from ..utils.file_helpers import delete_old_exports

attendance_bp = Blueprint('attendance', __name__)

@attendance_bp.route('/')
@login_required
def index():
    """メインページ（打刻画面）"""
    return render_template('index.html')

@attendance_bp.route('/punch', methods=['POST'])
@login_required
def punch():
    """打刻処理"""
    if not check_csrf():
        return redirect(url_for('attendance.index'))
    
    punch_type = request.form['type']
    description = request.form.get('description', '').strip()
    
    # フォームから送信されたタイムスタンプを使用、無い場合は現在時刻
    form_timestamp = request.form.get('timestamp', '').strip()
    if form_timestamp:
        try:
            # datetime-localフォーマットをISO形式に変換
            dt = datetime.fromisoformat(form_timestamp)
            timestamp = dt.isoformat()
        except (ValueError, TypeError):
            # 無効な日時の場合は現在時刻を使用
            timestamp = datetime.now().isoformat()
    else:
        timestamp = datetime.now().isoformat()
    
    # 入力検証
    if punch_type not in ['in', 'out']:
        flash("不正な打刻タイプです", "danger")
        return redirect(url_for('attendance.index'))
    
    if len(description) > 500:  # 文字数制限
        flash("業務内容は500文字以内で入力してください", "danger")
        return redirect(url_for('attendance.index'))
    
    # 重複チェック: 同じ日に同じタイプの打刻があるかチェック
    # timestampをdatetimeオブジェクトに変換して日付部分を取得
    timestamp_dt = datetime.fromisoformat(timestamp)
    date_part = timestamp_dt.strftime('%Y-%m-%d')  # YYYY-MM-DD
    start_date = date_part
    end_date = (datetime.strptime(date_part, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    
    existing_logs = Attendance.get_by_user_and_date_range(session['user_id'], start_date, end_date)
    existing_punch = None
    
    for log in existing_logs:
        log_date = log[0][:10]  # ログの日付部分
        if log_date == date_part and log[1] == punch_type:  # 同じ日、同じタイプ
            existing_punch = {
                'timestamp': log[0],
                'type': log[1], 
                'description': log[2] or ''
            }
            break
    
    # 重複がある場合は確認画面を表示
    if existing_punch:
        incoming_punch = {
            'timestamp': timestamp,
            'type': punch_type,
            'description': description
        }
        return render_template('confirm_punch.html', 
                             existing=existing_punch,
                             incoming=incoming_punch,
                             punch_type=punch_type,
                             day=date_part)
    
    try:
        Attendance.create(session['user_id'], timestamp, punch_type, description)
        
        action = "punch_in" if punch_type == "in" else "punch_out"
        log_audit_event(action, session['user_id'], session['user_name'])
        
        flash(f"{'出勤' if punch_type == 'in' else '退勤'}を記録しました", "success")
    except Exception as e:
        flash("打刻の記録に失敗しました", "danger")
    
    return redirect(url_for('attendance.index'))

@attendance_bp.route('/resolve_punch', methods=['POST'])
@login_required
def resolve_punch():
    """打刻の重複解決"""
    if not check_csrf():
        return redirect(url_for('attendance.index'))
    
    action = request.form['action']
    punch_type = request.form['type']
    timestamp = request.form['timestamp']
    description = request.form.get('description', '').strip()
    day = request.form['day']
    
    if action == 'overwrite':
        try:
            user_id = session['user_id']
            
            # 既存の同じタイプの記録のみを削除
            Attendance.delete_by_user_date_and_type(user_id, day, punch_type)
            
            # 新しい記録を作成
            Attendance.create(user_id, timestamp, punch_type, description)
            
            action_log = "punch_in" if punch_type == "in" else "punch_out"
            log_audit_event(action_log, user_id, session['user_name'])
            
            flash(f"{'出勤' if punch_type == 'in' else '退勤'}を記録しました（上書き）", "success")
        except Exception as e:
            flash("打刻の記録に失敗しました", "danger")
    elif action == 'keep':
        flash("既存の記録を保持しました", "info")
    
    return redirect(url_for('attendance.index'))


@attendance_bp.route('/my_logs')
@login_required
def view_my_logs():
    """個人の勤怠履歴表示"""
    # 古いエクスポートファイルを削除
    delete_old_exports()
    
    user_id = session['user_id']
    
    # 現在の月の開始日と終了日を取得
    now = datetime.now()
    year = request.args.get('year', now.year, type=int)
    month = request.args.get('month', now.month, type=int)
    
    # その月の全日付で勤怠ログを取得
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)
    
    # データベースから勤怠データを取得
    logs_data = Attendance.get_by_user_and_date_range(user_id, first_day.strftime('%Y-%m-%d'), last_day.strftime('%Y-%m-%d'))
    
    # 日付ごとにデータを整理
    logs = {}
    current_date = first_day
    weekdays = ['月', '火', '水', '木', '金', '土', '日']
    
    while current_date <= last_day:
        date_str = current_date.strftime('%Y-%m-%d')
        weekday = weekdays[current_date.weekday()]
        
        # その日の勤怠データを取得
        day_data = [log for log in logs_data if log[0][:10] == date_str]
        
        # 出勤・退勤データを分離
        in_data = next((log for log in day_data if log[1] == 'in'), None)
        out_data = next((log for log in day_data if log[1] == 'out'), None)
        
        # 時刻データを整形
        in_time_data = None
        out_time_data = None
        
        if in_data:
            time_part = in_data[0][11:16] if len(in_data[0]) > 16 else ''
            in_time_data = {'time': time_part}
            
        if out_data:
            time_part = out_data[0][11:16] if len(out_data[0]) > 16 else ''
            out_time_data = {'time': time_part, 'description': out_data[2]}
        
        # 残業時間計算（簡単な実装）
        overtime = ''
        if in_data and out_data:
            try:
                overtime_hours = calculate_overtime(in_data[0], out_data[0])
                if overtime_hours > 0:
                    overtime = f"{overtime_hours:.1f}h"
            except:
                overtime = ''
        
        logs[date_str] = {
            'weekday': weekday,
            'in': in_time_data,
            'out': out_time_data,
            'overtime': overtime
        }
        
        current_date += timedelta(days=1)
    
    return render_template('my_logs.html', logs=logs, year=year, month=month)

@attendance_bp.route('/export_csv', methods=['POST'])
@login_required
def export_csv():
    """個人CSV出力"""
    if not check_csrf():
        return redirect(url_for('attendance.view_my_logs'))
    
    year = int(request.form['year'])
    month = int(request.form['month'])
    
    # バリデーション
    current_year = datetime.now().year
    if not (2020 <= year <= current_year + 1):
        flash("有効な年を選択してください", "danger")
        return redirect(url_for('attendance.view_my_logs'))
    
    if not (1 <= month <= 12):
        flash("有効な月を選択してください", "danger")
        return redirect(url_for('attendance.view_my_logs'))
    
    try:
        user_name = session['user_name']
        user_id = session['user_id']
        overtime_threshold = User.get_overtime_threshold(user_id)
        
        # 一時ディレクトリでCSVファイルを生成
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_file = generate_csv(user_id, user_name, year, month, temp_dir, overtime_threshold)
            
            if csv_file and os.path.exists(csv_file):
                # エクスポートディレクトリにコピー
                exports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'exports', str(year), f"{month:02d}")
                os.makedirs(exports_dir, exist_ok=True)
                
                filename = f"{user_name}_{year}_{month:02d}_勤怠記録.csv"
                final_path = os.path.join(exports_dir, filename)
                
                import shutil
                shutil.copy2(csv_file, final_path)
                
                log_audit_event("csv_export", user_id, user_name)
                
                return send_file(final_path, as_attachment=True, download_name=filename)
            else:
                flash("CSVファイルの生成に失敗しました", "danger")
                
    except Exception as e:
        flash("CSVエクスポートに失敗しました", "danger")
    
    return redirect(url_for('attendance.view_my_logs'))

@attendance_bp.route('/import_csv', methods=['POST'])
@login_required
def import_csv():
    """CSV インポート"""
    if not check_csrf():
        return redirect(url_for('attendance.view_my_logs'))
    
    if 'file' not in request.files:
        flash("ファイルが選択されていません", "danger")
        return redirect(url_for('attendance.view_my_logs'))
    
    file = request.files['file']
    if file.filename == '':
        flash("ファイルが選択されていません", "danger")
        return redirect(url_for('attendance.view_my_logs'))
    
    if not file.filename.lower().endswith('.csv'):
        flash("CSVファイルを選択してください", "danger")
        return redirect(url_for('attendance.view_my_logs'))
    
    try:
        # CSVファイルを読み取り
        wrapper = TextIOWrapper(file.stream, encoding='utf-8-sig')
        reader = csv.DictReader(wrapper)
        
        # 既存データとの競合をチェック
        user_id = session['user_id']
        existing_records = Attendance.get_by_user(user_id)
        existing = defaultdict(dict)
        
        for row in existing_records:
            dt = safe_fromisoformat(row['timestamp'])
            day = dt.strftime('%Y/%m/%d')
            time_str = dt.strftime('%H:%M')
            existing[day][row['type']] = {
                'time': time_str,
                'description': row['description']
            }
        
        # インポートデータを処理
        incoming = defaultdict(dict)
        new_records = []
        
        for row in reader:
            raw_date = datetime.strptime(row['日付'], '%Y/%m/%d').strftime('%Y-%m-%d')
            
            for col, punch_type in [('出勤時刻', 'in'), ('退勤時刻', 'out')]:
                if row[col].strip():
                    time_str = normalize_time_str(row[col].strip())
                    if is_valid_time(time_str):
                        timestamp = f"{raw_date}T{time_str}:00"
                        description = row.get('業務内容', '').strip()
                        
                        incoming[raw_date][punch_type] = {
                            'timestamp': timestamp,
                            'description': description
                        }
        
        # 競合をチェック
        conflicts = []
        for date, types in incoming.items():
            date_formatted = datetime.strptime(date, '%Y-%m-%d').strftime('%Y/%m/%d')
            for punch_type, data in types.items():
                if date_formatted in existing and punch_type in existing[date_formatted]:
                    conflicts.append({
                        'date': date_formatted,
                        'type': punch_type,
                        'existing': existing[date_formatted][punch_type],
                        'incoming': data
                    })
        
        if conflicts:
            session['import_conflicts'] = conflicts
            session['import_data'] = incoming
            return render_template('resolve_conflicts.html', conflicts=conflicts)
        
        # 競合がない場合は直接インポート
        for date, types in incoming.items():
            for punch_type, data in types.items():
                new_records.append((user_id, data['timestamp'], punch_type, data['description']))
        
        if new_records:
            Attendance.bulk_insert(new_records)
            log_audit_event("csv_import", session['user_id'], session['user_name'])
            flash(f"{len(new_records)}件のデータをインポートしました", "success")
        else:
            flash("インポートするデータがありませんでした", "warning")
            
    except Exception as e:
        flash("CSVファイルの読み込みに失敗しました", "danger")
    
    return redirect(url_for('attendance.view_my_logs'))

@attendance_bp.route('/resolve_conflicts', methods=['POST'])
@login_required
def resolve_conflicts():
    """競合の解決"""
    if not check_csrf():
        return redirect(url_for('attendance.view_my_logs'))
    
    if 'import_conflicts' not in session or 'import_data' not in session:
        flash("セッションが無効です", "danger")
        return redirect(url_for('attendance.view_my_logs'))
    
    conflicts = session['import_conflicts']
    incoming_data = session['import_data']
    user_id = session['user_id']
    
    try:
        # 選択された解決方法に基づいて処理
        new_records = []
        dates_to_delete = set()
        
        for i, conflict in enumerate(conflicts):
            action = request.form.get(f'action_{i}')
            date = conflict['date']
            punch_type = conflict['type']
            
            if action == 'overwrite':
                # 既存データを削除してから新データを追加
                date_key = datetime.strptime(date, '%Y/%m/%d').strftime('%Y-%m-%d')
                dates_to_delete.add(date_key)
        
        # 競合解決の選択に基づいてデータを準備
        for date_str, types in incoming_data.items():
            date_formatted = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y/%m/%d')
            
            for punch_type, data in types.items():
                # 競合チェック
                conflict_found = False
                for i, conflict in enumerate(conflicts):
                    if conflict['date'] == date_formatted and conflict['type'] == punch_type:
                        action = request.form.get(f'action_{i}')
                        if action == 'skip':
                            conflict_found = True
                            break
                        elif action == 'overwrite':
                            # 削除対象に追加
                            dates_to_delete.add(date_str)
                
                if not conflict_found:
                    new_records.append((user_id, data['timestamp'], punch_type, data['description']))
        
        # 削除対象の日付のデータを削除
        for date_str in dates_to_delete:
            Attendance.delete_by_user_and_date(user_id, date_str)
        
        # 新しいデータを挿入
        if new_records:
            Attendance.bulk_insert(new_records)
        
        # セッションをクリア
        session.pop('import_conflicts', None)
        session.pop('import_data', None)
        
        log_audit_event("csv_import_resolved", user_id, session['user_name'])
        flash(f"{len(new_records)}件のデータをインポートしました", "success")
        
    except Exception as e:
        flash("データの更新に失敗しました", "danger")
    
    return redirect(url_for('attendance.view_my_logs'))

@attendance_bp.route('/edit_log/<date>')
@login_required
def edit_log(date):
    """勤怠ログ編集画面"""
    try:
        # 日付の妥当性チェック
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        flash("不正な日付です", "danger")
        return redirect(url_for('attendance.view_my_logs'))
    
    # 既存の勤怠データを取得
    user_id = session['user_id']
    start_date = date
    end_date = (datetime.strptime(date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    
    logs_data = Attendance.get_by_user_and_date_range(user_id, start_date, end_date)
    
    # 出勤・退勤データを分離
    in_time = ''
    out_time = ''
    description = ''
    
    for log in logs_data:
        if log[0][:10] == date:  # timestamp check (log[0] is timestamp)
            time_part = log[0][11:16] if len(log[0]) > 16 else ''
            if log[1] == 'in':  # type (log[1] is type)
                in_time = time_part
                if log[2]:  # description (log[2] is description)
                    description = log[2]
            elif log[1] == 'out':  # type
                out_time = time_part
                if log[2]:  # description - 退勤時の業務内容で上書き
                    description = log[2]
    
    return render_template('edit_log.html', date=date, in_time=in_time, out_time=out_time, description=description)

@attendance_bp.route('/update_log', methods=['POST'])
@login_required
def update_log():
    """勤怠ログ更新"""
    if not check_csrf():
        return redirect(url_for('attendance.view_my_logs'))
    
    date = request.form['date']
    in_time = request.form.get('in_time', '').strip()
    out_time = request.form.get('out_time', '').strip()
    description = request.form.get('description', '').strip()
    
    # バリデーション
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        flash("不正な日付です", "danger")
        return redirect(url_for('attendance.view_my_logs'))
    
    if in_time and not is_valid_time(in_time):
        flash("出勤時刻の形式が正しくありません", "danger")
        return redirect(url_for('attendance.edit_log', date=date))
    
    if out_time and not is_valid_time(out_time):
        flash("退勤時刻の形式が正しくありません", "danger")
        return redirect(url_for('attendance.edit_log', date=date))
    
    if len(description) > 500:
        flash("業務内容は500文字以内で入力してください", "danger")
        return redirect(url_for('attendance.edit_log', date=date))
    
    try:
        user_id = session['user_id']
        
        # 既存データを取得（空欄の場合は既存データを保持するため）
        start_date = date
        end_date = (datetime.strptime(date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        existing_logs = Attendance.get_by_user_and_date_range(user_id, start_date, end_date)
        
        # 既存の出勤・退勤データを分離
        existing_in_data = None
        existing_out_data = None
        
        for log in existing_logs:
            if log[0][:10] == date:  # timestamp check
                if log[1] == 'in':  # type
                    existing_in_data = log
                elif log[1] == 'out':  # type
                    existing_out_data = log
        
        # 既存データを削除
        Attendance.delete_by_user_and_date(user_id, date)
        
        # 新しいデータを挿入（空欄の場合は既存データを保持）
        new_records = []
        
        # 出勤時刻の処理
        if in_time:
            # 新しい出勤時刻が入力された場合
            timestamp = f"{date}T{in_time}:00"
            new_records.append((user_id, timestamp, 'in', description))
        elif existing_in_data:
            # 出勤時刻が空欄で既存データがある場合は既存データを保持
            new_records.append((user_id, existing_in_data[0], 'in', description if description else existing_in_data[2]))
        
        # 退勤時刻の処理
        if out_time:
            # 新しい退勤時刻が入力された場合
            timestamp = f"{date}T{out_time}:00"
            new_records.append((user_id, timestamp, 'out', description))
        elif existing_out_data:
            # 退勤時刻が空欄で既存データがある場合は既存データを保持
            new_records.append((user_id, existing_out_data[0], 'out', description if description else existing_out_data[2]))
        
        if new_records:
            Attendance.bulk_insert(new_records)
        
        log_audit_event("attendance_edit", user_id, session['user_name'])
        flash("勤怠記録を更新しました", "success")
        
    except Exception as e:
        flash("勤怠記録の更新に失敗しました", "danger")
    
    return redirect(url_for('attendance.view_my_logs'))