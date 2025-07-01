import re
from datetime import datetime

__all__ = [
    'is_valid_email',
    'is_valid_time',
    'get_client_info',
    'safe_fromisoformat',
    'normalize_time_str',
    'calculate_overtime',
    'sanitize_filename',
]

def is_valid_email(email: str) -> bool:
    """Return True if the given string is a valid email."""
    return bool(re.match(r'^[^@]+@[^@]+\.[^@]+$', email))


def is_valid_time(time_str: str) -> bool:
    """Return True if time_str is HH:MM format."""
    try:
        datetime.strptime(time_str, '%H:%M')
        return True
    except ValueError:
        return False


def get_client_info(ua: str):
    """Guess device type and OS name from User-Agent."""
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


def safe_fromisoformat(ts: str) -> datetime:
    """Parse datetime from ISO format safely."""
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


def normalize_time_str(time_str: str) -> str:
    """Normalize time string to HH:MM."""
    try:
        dt = datetime.strptime(time_str, '%H:%M')
        return dt.strftime('%H:%M')
    except ValueError:
        return time_str


def calculate_overtime(out_time: str, threshold: str = '18:00', in_time: str | None = None) -> str:
    """Return overtime string calculated from out_time, threshold and optional in_time."""
    try:
        out_dt = datetime.strptime(out_time, '%H:%M')
        start_dt = datetime.strptime(threshold or '18:00', '%H:%M')
        if in_time:
            try:
                in_dt = datetime.strptime(in_time, '%H:%M')
                if in_dt > start_dt:
                    start_dt = in_dt
            except ValueError:
                pass
        if out_dt > start_dt:
            delta = out_dt - start_dt
            hours, minutes = divmod(delta.seconds // 60, 60)
            return f"{hours:02d}:{minutes:02d}"
    except ValueError:
        return ''
    return ''


def sanitize_filename(name: str) -> str:
    """Return a filename-safe string made of alphanumerics, hyphen and underscore."""
    return re.sub(r'[^A-Za-z0-9_-]+', '', name)

