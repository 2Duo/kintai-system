import re
from datetime import datetime

def is_valid_email(email: str) -> bool:
    """メールアドレスの形式を検証"""
    if not email or len(email) > 320:  # RFC 5321 limit
        return False
    
    # より厳密なメールアドレス検証
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    
    # ローカル部の長さチェック（64文字まで）
    local, domain = email.rsplit('@', 1)
    if len(local) > 64:
        return False
    
    return True

def is_valid_time(time_str: str) -> bool:
    """時刻形式（HH:MM）の検証"""
    if not time_str:
        return False
    
    try:
        datetime.strptime(time_str, '%H:%M')
        return True
    except ValueError:
        return False

def is_valid_password(password: str) -> tuple[bool, str]:
    """パスワードの強度を検証"""
    if not password:
        return False, "パスワードを入力してください"
    
    if len(password) < 8:
        return False, "パスワードは8文字以上で入力してください"
    
    if len(password) > 128:
        return False, "パスワードは128文字以内で入力してください"
    
    # 複雑度チェック
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    complexity_count = sum([has_upper, has_lower, has_digit, has_special])
    
    if complexity_count < 3:
        return False, "パスワードには大文字、小文字、数字、記号のうち3種類以上を含めてください"
    
    return True, ""

def validate_user_input(name: str, email: str, password: str = None) -> tuple[bool, str]:
    """ユーザー入力の包括的検証"""
    # 名前の検証
    if not name or not name.strip():
        return False, "名前を入力してください"
    
    name = name.strip()
    if len(name) > 100:
        return False, "名前は100文字以内で入力してください"
    
    # HTMLタグやスクリプトの検出
    if '<' in name or '>' in name or 'script' in name.lower():
        return False, "名前に無効な文字が含まれています"
    
    # メールアドレスの検証
    if not email or not email.strip():
        return False, "メールアドレスを入力してください"
    
    email = email.strip().lower()
    if not is_valid_email(email):
        return False, "有効なメールアドレスを入力してください"
    
    # パスワードの検証（新規作成時のみ）
    if password is not None:
        is_valid, message = is_valid_password(password)
        if not is_valid:
            return False, message
    
    return True, ""

def sanitize_text_input(text: str, max_length: int = 1000) -> str:
    """テキスト入力のサニタイズ"""
    if not text:
        return ""
    
    # 基本的なサニタイズ
    text = text.strip()
    
    # 長さ制限
    if len(text) > max_length:
        text = text[:max_length]
    
    # 制御文字の除去（タブ、改行は保持）
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\t\n\r')
    
    return text

def validate_date_range(year: int, month: int) -> tuple[bool, str]:
    """年月の妥当性を検証"""
    current_year = datetime.now().year
    
    if not (2020 <= year <= current_year + 1):
        return False, "有効な年を選択してください（2020年以降）"
    
    if not (1 <= month <= 12):
        return False, "有効な月を選択してください（1-12）"
    
    return True, ""