import smtplib
from email.message import EmailMessage
from ..models import MailSettings
import html

def send_email(to_address: str, subject: str, body: str) -> tuple[bool, str]:
    """メール送信"""
    try:
        # メール設定を取得
        settings = MailSettings.get()
        if not settings:
            return False, "メール設定が見つかりません"
        
        # 設定の検証
        if not settings['server'] or not settings['port']:
            return False, "メールサーバー設定が不完全です"
        
        # メール作成
        msg = EmailMessage()
        msg['From'] = settings['username'] or 'noreply@example.com'
        msg['To'] = to_address
        msg['Subject'] = subject
        msg.set_content(body)
        
        # SMTP接続でメール送信
        with smtplib.SMTP(settings['server'], int(settings['port'])) as smtp:
            if settings.get('use_tls'):
                smtp.starttls()
            
            if settings.get('username') and settings.get('password'):
                smtp.login(settings['username'], settings.get('password', ''))
            
            smtp.send_message(msg)
        
        return True, "メールを送信しました"
        
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP認証に失敗しました"
    except smtplib.SMTPRecipientsRefused:
        return False, "受信者のメールアドレスが拒否されました"
    except smtplib.SMTPServerDisconnected:
        return False, "SMTPサーバーとの接続が切断されました"
    except Exception as e:
        return False, f"メール送信エラー: {str(e)}"

def validate_email_settings(server: str, port: int, username: str = None, password: str = None, use_tls: bool = True) -> tuple[bool, str]:
    """メール設定の妥当性を検証"""
    try:
        # 基本的な設定チェック
        if not server or not server.strip():
            return False, "SMTPサーバーが指定されていません"
        
        if not (1 <= port <= 65535):
            return False, "ポート番号が無効です（1-65535）"
        
        # SMTP接続テスト
        with smtplib.SMTP(server, port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            
            if username and password:
                smtp.login(username, password)
        
        return True, "メール設定は有効です"
        
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP認証に失敗しました（ユーザー名またはパスワードが間違っています）"
    except smtplib.SMTPServerDisconnected:
        return False, "SMTPサーバーに接続できません"
    except smtplib.SMTPConnectError:
        return False, "SMTPサーバーに接続できません（サーバーまたはポート番号を確認してください）"
    except Exception as e:
        return False, f"設定検証エラー: {str(e)}"

def format_email_template(template: str, **kwargs) -> str:
    """メールテンプレートのフォーマット"""
    try:
        # HTMLエスケープ
        safe_kwargs = {k: html.escape(str(v)) if v is not None else '' for k, v in kwargs.items()}
        
        # テンプレート変数を置換
        formatted = template.format(**safe_kwargs)
        
        return formatted
        
    except KeyError as e:
        raise ValueError(f"テンプレート変数が見つかりません: {e}")
    except Exception as e:
        raise ValueError(f"テンプレートフォーマットエラー: {str(e)}")

def send_notification_email(to_address: str, notification_type: str, **data) -> tuple[bool, str]:
    """通知メールを送信"""
    try:
        # メール設定を取得
        settings = MailSettings.get()
        if not settings:
            return False, "メール設定が見つかりません"
        
        # テンプレートを取得
        subject_template = settings.get('subject_template', '通知')
        body_template = settings.get('body_template', '{message}')
        
        # 通知タイプ別のデフォルトメッセージ
        default_messages = {
            'user_created': 'アカウントが作成されました',
            'password_reset': 'パスワードがリセットされました',
            'attendance_reminder': '勤怠記録の確認をお願いします',
            'system_maintenance': 'システムメンテナンスのお知らせ'
        }
        
        # メッセージデータを準備
        message_data = {
            'notification_type': notification_type,
            'message': default_messages.get(notification_type, '通知があります'),
            **data
        }
        
        # テンプレートをフォーマット
        subject = format_email_template(subject_template, **message_data)
        body = format_email_template(body_template, **message_data)
        
        # メール送信
        return send_email(to_address, subject, body)
        
    except Exception as e:
        return False, f"通知メール送信エラー: {str(e)}"

def send_bulk_email(recipients: list, subject: str, body: str) -> tuple[int, list]:
    """一括メール送信"""
    success_count = 0
    errors = []
    
    for recipient in recipients:
        try:
            success, message = send_email(recipient, subject, body)
            if success:
                success_count += 1
            else:
                errors.append(f"{recipient}: {message}")
        except Exception as e:
            errors.append(f"{recipient}: {str(e)}")
    
    return success_count, errors

def test_email_connection() -> tuple[bool, str]:
    """メール接続をテスト"""
    try:
        settings = MailSettings.get()
        if not settings:
            return False, "メール設定が見つかりません"
        
        return validate_email_settings(
            settings['server'],
            int(settings['port']),
            settings.get('username'),
            settings.get('password'),
            bool(settings.get('use_tls', True))
        )
        
    except Exception as e:
        return False, f"接続テストエラー: {str(e)}"

def sanitize_email_content(content: str) -> str:
    """メール内容をサニタイズ"""
    if not content:
        return ""
    
    # HTMLエスケープ
    content = html.escape(content)
    
    # 不正な文字の除去
    content = ''.join(char for char in content if ord(char) >= 32 or char in '\t\n\r')
    
    # 長さ制限（10000文字）
    if len(content) > 10000:
        content = content[:10000] + "..."
    
    return content

def parse_email_addresses(address_string: str) -> list:
    """メールアドレス文字列をパースして配列に変換"""
    if not address_string:
        return []
    
    # カンマ、セミコロン、改行で分割
    import re
    addresses = re.split(r'[,;\n]', address_string)
    
    # 各アドレスをクリーンアップ
    clean_addresses = []
    for addr in addresses:
        addr = addr.strip()
        if addr and '@' in addr:
            clean_addresses.append(addr)

    return clean_addresses


def send_registration_email(to_email: str, name: str) -> tuple[bool, str]:
    """ユーザー登録通知メールを送信"""
    return send_notification_email(to_email, 'user_created', name=name)
