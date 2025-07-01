from datetime import datetime
import re

def safe_fromisoformat(ts: str) -> datetime:
    """ISO形式の日時文字列を安全にパース"""
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        # 時刻部分の0埋めを修正
        parts = ts.split('T')
        if len(parts) == 2:
            date_part, time_part = parts
            time_components = time_part.split(':')
            if len(time_components) >= 2 and len(time_components[0]) == 1:
                time_part = '0' + time_part
                ts = f"{date_part}T{time_part}"
        return datetime.fromisoformat(ts)

def normalize_time_str(time_str: str) -> str:
    """時刻文字列をHH:MM形式に正規化"""
    if not time_str:
        return ""
    
    try:
        # 様々な形式に対応
        time_str = time_str.strip()
        
        # "HH:MM:SS" -> "HH:MM"
        if time_str.count(':') == 2:
            time_str = ':'.join(time_str.split(':')[:2])
        
        # "H:MM" -> "HH:MM"
        if ':' in time_str:
            parts = time_str.split(':')
            if len(parts) == 2:
                hour, minute = parts
                hour = hour.zfill(2)
                minute = minute.zfill(2)
                time_str = f"{hour}:{minute}"
        
        # "HHMM" -> "HH:MM"
        elif len(time_str) == 4 and time_str.isdigit():
            time_str = f"{time_str[:2]}:{time_str[2:]}"
        
        # "HMM" -> "HH:MM"
        elif len(time_str) == 3 and time_str.isdigit():
            time_str = f"0{time_str[0]}:{time_str[1:]}"
        
        # 形式チェック
        dt = datetime.strptime(time_str, '%H:%M')
        return dt.strftime('%H:%M')
        
    except ValueError:
        return time_str

def calculate_overtime(out_time: str, threshold: str = '18:00', in_time: str = None) -> str:
    """残業時間を計算"""
    if not out_time:
        return ''
    
    try:
        out_dt = datetime.strptime(out_time, '%H:%M')
        start_dt = datetime.strptime(threshold or '18:00', '%H:%M')
        
        # 出勤時間が残業開始時刻より遅い場合は出勤時間を基準とする
        if in_time:
            try:
                in_dt = datetime.strptime(in_time, '%H:%M')
                if in_dt > start_dt:
                    start_dt = in_dt
            except ValueError:
                pass
        
        # 残業時間計算
        if out_dt > start_dt:
            delta = out_dt - start_dt
            total_minutes = delta.seconds // 60
            hours, minutes = divmod(total_minutes, 60)
            return f"{hours:02d}:{minutes:02d}"
            
    except ValueError:
        pass
    
    return ''

def format_datetime_for_display(dt: datetime) -> str:
    """表示用の日時形式にフォーマット"""
    return dt.strftime('%Y/%m/%d %H:%M')

def format_date_for_display(dt: datetime) -> str:
    """表示用の日付形式にフォーマット"""
    return dt.strftime('%Y/%m/%d')

def format_time_for_display(dt: datetime) -> str:
    """表示用の時刻形式にフォーマット"""
    return dt.strftime('%H:%M')

def parse_date_input(date_str: str) -> datetime:
    """ユーザー入力の日付文字列をパース"""
    if not date_str:
        raise ValueError("日付が入力されていません")
    
    # 様々な日付形式に対応
    formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%Y年%m月%d日',
        '%m/%d/%Y',
        '%d/%m/%Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    
    raise ValueError(f"日付形式が認識できません: {date_str}")

def get_month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """指定された年月の開始日と終了日を取得"""
    start = datetime(year, month, 1)
    
    # 次の月の1日を取得してから1日引く
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    
    return start, end

def is_weekend(dt: datetime) -> bool:
    """週末かどうかを判定（土日）"""
    return dt.weekday() >= 5  # 5=土曜日, 6=日曜日

def get_weekday_name(dt: datetime) -> str:
    """曜日名を取得"""
    weekdays = ['月', '火', '水', '木', '金', '土', '日']
    return weekdays[dt.weekday()]