import os
from datetime import datetime
from flask import request, current_app

def get_client_info(user_agent: str = None) -> tuple[str, str]:
    """User-Agentからデバイス情報を推測"""
    if not user_agent:
        user_agent = request.headers.get('User-Agent', '') if request else ''
    
    ua_lower = user_agent.lower()
    
    # OS判定
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
        os_name = 'Unknown'
    
    # デバイス判定
    if 'ipad' in ua_lower or 'tablet' in ua_lower or ('android' in ua_lower and 'mobile' not in ua_lower):
        device = 'tablet'
    elif 'iphone' in ua_lower or ('android' in ua_lower and 'mobile' in ua_lower):
        device = 'smartphone'
    else:
        device = 'pc'
    
    return device, os_name

def log_audit_event(action: str, user_id: int = None, user_name: str = None, details: str = None):
    """監査ログを記録"""
    try:
        # ログファイルパスを取得
        audit_log_path = os.environ.get(
            'AUDIT_LOG_PATH', 
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs', 'audit.log')
        )
        
        # ログディレクトリを作成
        os.makedirs(os.path.dirname(audit_log_path), exist_ok=True)
        
        # リクエスト情報を取得
        ip_address = 'N/A'
        user_agent = 'N/A'
        device = 'N/A'
        os_name = 'N/A'
        
        if request:
            ip_address = request.remote_addr or 'N/A'
            user_agent = request.headers.get('User-Agent', 'N/A')
            device, os_name = get_client_info(user_agent)
        
        # ログエントリを作成
        timestamp = datetime.now().isoformat()
        log_entry = {
            'timestamp': timestamp,
            'action': action,
            'user_id': user_id,
            'user_name': user_name or 'N/A',
            'ip_address': ip_address,
            'device': device,
            'os': os_name,
            'user_agent': user_agent[:200] if user_agent != 'N/A' else 'N/A',  # 長さ制限
            'details': details or ''
        }
        
        # ログ行を構築
        line = f"[{timestamp}] {action} | User: {user_name or 'N/A'} (ID: {user_id or 'N/A'}) | IP: {ip_address} | Device: {device}/{os_name}"
        if details:
            line += f" | Details: {details}"
        line += "\n"
        
        # ファイルに書き込み
        with open(audit_log_path, 'a', encoding='utf-8') as f:
            f.write(line)
            
    except Exception as e:
        # 監査ログの記録に失敗してもアプリケーションを停止させない
        # 代わりにアプリケーションログに記録
        if current_app:
            current_app.logger.error(f"Failed to write audit log: {str(e)}")

def clear_audit_log():
    """監査ログをクリア"""
    try:
        audit_log_path = os.environ.get(
            'AUDIT_LOG_PATH', 
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs', 'audit.log')
        )
        
        if os.path.exists(audit_log_path):
            os.remove(audit_log_path)
            return True
            
    except Exception:
        pass
    
    return False

def get_audit_log_entries(limit: int = 500) -> list[str]:
    """監査ログエントリを取得"""
    try:
        audit_log_path = os.environ.get(
            'AUDIT_LOG_PATH', 
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs', 'audit.log')
        )
        
        if not os.path.exists(audit_log_path):
            return []
        
        with open(audit_log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 最新のエントリから指定数を返す
        return list(reversed(lines[-limit:]))
        
    except Exception:
        return []

# 監査対象アクションの定義
AUDIT_ACTIONS = {
    'login': 'ユーザーログイン',
    'login_failed': 'ログイン失敗',
    'logout': 'ユーザーログアウト',
    'password_change': 'パスワード変更',
    'punch_in': '出勤打刻',
    'punch_out': '退勤打刻',
    'attendance_edit': '勤怠記録編集',
    'csv_import': 'CSV インポート',
    'csv_import_resolved': 'CSV インポート（競合解決）',
    'csv_export': 'CSV エクスポート',
    'admin_export_single': '管理者単体エクスポート',
    'admin_export_bulk': '管理者一括エクスポート',
    'user_created': 'ユーザー作成',
    'user_updated': 'ユーザー更新',
    'user_deleted': 'ユーザー削除',
    'mail_settings_updated': 'メール設定更新',
    'system_setup': 'システム初期設定',
    'system_updated': 'システム更新',
    'message_sent': 'メッセージ送信',
    'file_download': 'ファイルダウンロード',
    'security_violation': 'セキュリティ違反'
}