import csv
import os
from datetime import datetime, timedelta
from collections import defaultdict
from ..models import Attendance, User
from .datetime_helpers import safe_fromisoformat, calculate_overtime

def generate_csv(user_id: int, name: str, year: int, month: int, target_dir: str, overtime_threshold: str = '18:00') -> str:
    """ユーザーの勤怠データからCSVファイルを生成"""
    try:
        # 対象月の範囲を計算
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
        
        # 勤怠データを取得
        records = Attendance.get_by_user_and_date_range(
            user_id, 
            start.isoformat(), 
            end.isoformat()
        )
        
        # 日別にデータを整理
        daily_data = defaultdict(lambda: {'in': '', 'out': '', 'description': ''})
        
        for row in records:
            dt = safe_fromisoformat(row['timestamp'])
            day = dt.strftime('%Y/%m/%d')
            time_str = dt.strftime('%H:%M')
            
            if row['type'] == 'in':
                daily_data[day]['in'] = time_str
                if row['description']:
                    daily_data[day]['description'] = row['description']
            elif row['type'] == 'out':
                daily_data[day]['out'] = time_str
                if row['description'] and not daily_data[day]['description']:
                    daily_data[day]['description'] = row['description']
        
        # CSVファイルを生成
        safe_name = sanitize_filename(name)
        filename = f"{safe_name}_{year}_{month:02d}_勤怠記録.csv"
        filepath = os.path.join(target_dir, filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            # ヘッダー行
            writer.writerow(['日付', '出勤時刻', '退勤時刻', '業務内容', '残業時間'])
            
            # 月の全日を出力
            current_date = start
            while current_date < end:
                day_str = current_date.strftime('%Y/%m/%d')
                data = daily_data.get(day_str, {'in': '', 'out': '', 'description': ''})
                
                # 残業時間を計算
                overtime = ''
                if data['out']:
                    overtime = calculate_overtime(data['out'], overtime_threshold, data['in'])
                
                writer.writerow([
                    day_str,
                    data['in'],
                    data['out'],
                    data['description'],
                    overtime
                ])
                
                current_date += timedelta(days=1)
        
        return filepath
        
    except Exception as e:
        raise Exception(f"CSV生成エラー: {str(e)}")

def parse_csv_file(file_stream, user_id: int) -> dict:
    """CSVファイルを解析して勤怠データを抽出"""
    try:
        from io import TextIOWrapper
        
        # ファイルストリームをテキストとして読み取り
        if hasattr(file_stream, 'stream'):
            wrapper = TextIOWrapper(file_stream.stream, encoding='utf-8-sig')
        else:
            wrapper = TextIOWrapper(file_stream, encoding='utf-8-sig')
        
        reader = csv.DictReader(wrapper)
        
        # 必要なカラムの存在チェック
        required_columns = ['日付', '出勤時刻', '退勤時刻']
        if not all(col in reader.fieldnames for col in required_columns):
            raise ValueError("必要なカラム（日付、出勤時刻、退勤時刻）が見つかりません")
        
        # データを解析
        parsed_data = {}
        for row_num, row in enumerate(reader, start=2):  # ヘッダー行の次から
            try:
                # 日付の解析
                date_str = row['日付'].strip()
                if not date_str:
                    continue
                
                # 日付形式の統一
                try:
                    date_obj = datetime.strptime(date_str, '%Y/%m/%d')
                    date_key = date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        date_key = date_str
                    except ValueError:
                        raise ValueError(f"行{row_num}: 日付形式が不正です ({date_str})")
                
                parsed_data[date_key] = {
                    'in_time': row.get('出勤時刻', '').strip(),
                    'out_time': row.get('退勤時刻', '').strip(),
                    'description': row.get('業務内容', '').strip()
                }
                
            except Exception as e:
                raise ValueError(f"行{row_num}: {str(e)}")
        
        return parsed_data
        
    except Exception as e:
        raise Exception(f"CSV解析エラー: {str(e)}")

def detect_conflicts(parsed_data: dict, user_id: int) -> list:
    """既存データとの競合を検出"""
    try:
        # 既存の勤怠データを取得
        existing_records = Attendance.get_by_user(user_id)
        existing_data = defaultdict(dict)
        
        for record in existing_records:
            dt = safe_fromisoformat(record['timestamp'])
            date_key = dt.strftime('%Y-%m-%d')
            time_str = dt.strftime('%H:%M')
            
            existing_data[date_key][record['type']] = {
                'time': time_str,
                'description': record['description']
            }
        
        # 競合をチェック
        conflicts = []
        for date_key, new_data in parsed_data.items():
            date_formatted = datetime.strptime(date_key, '%Y-%m-%d').strftime('%Y/%m/%d')
            
            # 出勤時刻の競合チェック
            if new_data['in_time'] and date_formatted in existing_data and 'in' in existing_data[date_formatted]:
                conflicts.append({
                    'date': date_formatted,
                    'type': 'in',
                    'existing': existing_data[date_formatted]['in'],
                    'new': {
                        'time': new_data['in_time'],
                        'description': new_data['description']
                    }
                })
            
            # 退勤時刻の競合チェック
            if new_data['out_time'] and date_formatted in existing_data and 'out' in existing_data[date_formatted]:
                conflicts.append({
                    'date': date_formatted,
                    'type': 'out',
                    'existing': existing_data[date_formatted]['out'],
                    'new': {
                        'time': new_data['out_time'],
                        'description': new_data['description']
                    }
                })
        
        return conflicts
        
    except Exception as e:
        raise Exception(f"競合検出エラー: {str(e)}")

def prepare_import_records(parsed_data: dict, user_id: int, conflict_resolutions: dict = None) -> list:
    """インポート用のレコードを準備"""
    records = []
    
    for date_key, data in parsed_data.items():
        # 競合解決の確認
        skip_in = False
        skip_out = False
        
        if conflict_resolutions:
            for conflict_key, action in conflict_resolutions.items():
                if conflict_key.startswith(f"{date_key}_in") and action == 'skip':
                    skip_in = True
                elif conflict_key.startswith(f"{date_key}_out") and action == 'skip':
                    skip_out = True
        
        # 出勤記録
        if data['in_time'] and not skip_in:
            from .datetime_helpers import normalize_time_str
            from .validators import is_valid_time
            
            in_time = normalize_time_str(data['in_time'])
            if is_valid_time(in_time):
                timestamp = f"{date_key}T{in_time}:00"
                records.append((user_id, timestamp, 'in', data['description']))
        
        # 退勤記録
        if data['out_time'] and not skip_out:
            from .datetime_helpers import normalize_time_str
            from .validators import is_valid_time
            
            out_time = normalize_time_str(data['out_time'])
            if is_valid_time(out_time):
                timestamp = f"{date_key}T{out_time}:00"
                records.append((user_id, timestamp, 'out', data['description']))
    
    return records

def sanitize_filename(name: str) -> str:
    """ファイル名として安全な文字列に変換"""
    import re
    # 英数字、ハイフン、アンダースコアのみを許可
    safe_name = re.sub(r'[^A-Za-z0-9_-]+', '', name)
    
    # 空文字列の場合はデフォルト名を使用
    if not safe_name:
        safe_name = 'user'
    
    return safe_name

def validate_csv_structure(file_stream) -> tuple[bool, str]:
    """CSVファイルの構造を検証"""
    try:
        from io import TextIOWrapper
        
        # ファイルサイズチェック（10MB制限）
        if hasattr(file_stream, 'content_length') and file_stream.content_length > 10 * 1024 * 1024:
            return False, "ファイルサイズが10MBを超えています"
        
        # ファイルストリームをテキストとして読み取り
        if hasattr(file_stream, 'stream'):
            wrapper = TextIOWrapper(file_stream.stream, encoding='utf-8-sig')
        else:
            wrapper = TextIOWrapper(file_stream, encoding='utf-8-sig')
        
        reader = csv.DictReader(wrapper)
        
        # 必要なカラムの存在チェック
        required_columns = ['日付', '出勤時刻', '退勤時刻']
        missing_columns = [col for col in required_columns if col not in reader.fieldnames]
        
        if missing_columns:
            return False, f"必要なカラムが見つかりません: {', '.join(missing_columns)}"
        
        # 行数チェック（1000行制限）
        row_count = 0
        for _ in reader:
            row_count += 1
            if row_count > 1000:
                return False, "データが1000行を超えています"
        
        return True, ""
        
    except UnicodeDecodeError:
        return False, "ファイルのエンコーディングが正しくありません（UTF-8を使用してください）"
    except Exception as e:
        return False, f"ファイル構造の検証に失敗しました: {str(e)}"