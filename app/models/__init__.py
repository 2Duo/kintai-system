from flask import Blueprint, current_app, g
import sqlite3
import os
from werkzeug.security import generate_password_hash

models_bp = Blueprint('models', __name__)

class BaseModel:
    """ベースモデルクラス"""
    
    @staticmethod
    def get_db():
        """データベース接続を取得"""
        return current_app.get_db()

class User(BaseModel):
    """ユーザーモデル"""
    
    @staticmethod
    def create(email, name, password, is_admin=False, is_superadmin=False, overtime_threshold='18:00'):
        """ユーザーを作成"""
        db = User.get_db()
        c = db.cursor()
        password_hash = generate_password_hash(password)
        
        c.execute("""
            INSERT INTO users (email, name, password_hash, is_admin, is_superadmin, overtime_threshold)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (email, name, password_hash, int(is_admin), int(is_superadmin), overtime_threshold))
        db.commit()
        return c.lastrowid
    
    @staticmethod
    def get_by_email(email):
        """メールアドレスでユーザーを取得"""
        db = User.get_db()
        c = db.cursor()
        c.execute("""
            SELECT id, email, name, password_hash, is_admin, is_superadmin, overtime_threshold
            FROM users WHERE email = ?
        """, (email,))
        return c.fetchone()
    
    @staticmethod
    def get_by_id(user_id):
        """IDでユーザーを取得"""
        db = User.get_db()
        c = db.cursor()
        c.execute("""
            SELECT id, email, name, password_hash, is_admin, is_superadmin, overtime_threshold
            FROM users WHERE id = ?
        """, (user_id,))
        return c.fetchone()
    
    @staticmethod
    def get_name_by_id(user_id):
        """IDでユーザー名を取得"""
        db = User.get_db()
        c = db.cursor()
        c.execute("SELECT name FROM users WHERE id = ?", (user_id,))
        result = c.fetchone()
        return result[0] if result else None
    
    @staticmethod
    def update_password(user_id, new_password):
        """パスワードを更新"""
        db = User.get_db()
        c = db.cursor()
        password_hash = generate_password_hash(new_password)
        c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        db.commit()
    
    @staticmethod
    def get_overtime_threshold(user_id, default='18:00'):
        """残業開始時刻を取得"""
        db = User.get_db()
        c = db.cursor()
        c.execute("SELECT overtime_threshold FROM users WHERE id = ?", (user_id,))
        result = c.fetchone()
        return result[0] if result else default
    
    @staticmethod
    def get_all():
        """全ユーザーを取得"""
        db = User.get_db()
        c = db.cursor()
        c.execute("SELECT id, email, name, is_admin, is_superadmin FROM users ORDER BY name")
        return c.fetchall()
    
    @staticmethod
    def update(user_id, email, name, is_admin=False, is_superadmin=False, overtime_threshold='18:00'):
        """ユーザー情報を更新"""
        db = User.get_db()
        c = db.cursor()
        c.execute("""
            UPDATE users SET email = ?, name = ?, is_admin = ?, is_superadmin = ?, overtime_threshold = ?
            WHERE id = ?
        """, (email, name, int(is_admin), int(is_superadmin), overtime_threshold, user_id))
        db.commit()
    
    @staticmethod
    def delete(user_id):
        """ユーザーを削除"""
        db = User.get_db()
        c = db.cursor()
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
    
    @staticmethod
    def get_managed_users(admin_id):
        """管理対象ユーザーを取得"""
        db = User.get_db()
        c = db.cursor()
        c.execute("""
            SELECT u.id, u.name FROM users u
            INNER JOIN admin_managed_users m ON u.id = m.user_id
            WHERE m.admin_id = ?
            ORDER BY u.name
        """, (admin_id,))
        return c.fetchall()

class Attendance(BaseModel):
    """勤怠モデル"""
    
    @staticmethod
    def create(user_id, timestamp, punch_type, description=''):
        """勤怠記録を作成"""
        db = Attendance.get_db()
        c = db.cursor()
        c.execute("""
            INSERT INTO attendance (user_id, timestamp, type, description)
            VALUES (?, ?, ?, ?)
        """, (user_id, timestamp, punch_type, description))
        db.commit()
        return c.lastrowid
    
    @staticmethod
    def get_by_user_and_date_range(user_id, start_date, end_date):
        """ユーザーと日付範囲で勤怠記録を取得"""
        db = Attendance.get_db()
        c = db.cursor()
        c.execute("""
            SELECT timestamp, type, description FROM attendance
            WHERE user_id = ? AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
        """, (user_id, start_date, end_date))
        return c.fetchall()
    
    @staticmethod
    def get_by_user(user_id):
        """ユーザーの全勤怠記録を取得"""
        db = Attendance.get_db()
        c = db.cursor()
        c.execute("""
            SELECT timestamp, type, description FROM attendance 
            WHERE user_id = ? ORDER BY timestamp
        """, (user_id,))
        return c.fetchall()
    
    @staticmethod
    def delete_by_user_and_date(user_id, date):
        """ユーザーの特定日の勤怠記録を削除"""
        db = Attendance.get_db()
        c = db.cursor()
        c.execute("""
            DELETE FROM attendance 
            WHERE user_id = ? AND date(timestamp) = ?
        """, (user_id, date))
        db.commit()
    
    @staticmethod
    def delete_by_user_date_and_type(user_id, date, punch_type):
        """ユーザーの特定日・特定タイプの勤怠記録を削除"""
        db = Attendance.get_db()
        c = db.cursor()
        c.execute("""
            DELETE FROM attendance 
            WHERE user_id = ? AND date(timestamp) = ? AND type = ?
        """, (user_id, date, punch_type))
        db.commit()
    
    @staticmethod
    def bulk_insert(records):
        """勤怠記録の一括挿入"""
        db = Attendance.get_db()
        c = db.cursor()
        c.executemany("""
            INSERT INTO attendance (user_id, timestamp, type, description)
            VALUES (?, ?, ?, ?)
        """, records)
        db.commit()

class Message(BaseModel):
    """メッセージモデル"""
    
    @staticmethod
    def create(sender_id, recipient_id, message):
        """メッセージを作成"""
        from datetime import datetime
        db = Message.get_db()
        c = db.cursor()
        timestamp = datetime.now().isoformat()
        c.execute("""
            INSERT INTO messages (sender_id, recipient_id, message, timestamp)
            VALUES (?, ?, ?, ?)
        """, (sender_id, recipient_id, message, timestamp))
        db.commit()
        return c.lastrowid
    
    @staticmethod
    def get_conversation(user1_id, user2_id, limit=20):
        """会話を取得"""
        db = Message.get_db()
        c = db.cursor()
        c.execute("""
            SELECT id, sender_id, recipient_id, message, timestamp, is_read
            FROM messages
            WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?)
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user1_id, user2_id, user2_id, user1_id, limit))
        return list(reversed(c.fetchall()))
    
    @staticmethod
    def mark_as_read(user_id, partner_id):
        """メッセージを既読にする"""
        from datetime import datetime
        db = Message.get_db()
        c = db.cursor()
        read_timestamp = datetime.now().isoformat()
        c.execute("""
            UPDATE messages SET is_read = 1, read_timestamp = ?
            WHERE recipient_id = ? AND sender_id = ? AND is_read = 0
        """, (read_timestamp, user_id, partner_id))
        db.commit()
    
    @staticmethod
    def get_unread_count(user_id):
        """未読メッセージ数を取得"""
        db = Message.get_db()
        c = db.cursor()
        c.execute("""
            SELECT COUNT(*) FROM messages 
            WHERE recipient_id = ? AND is_read = 0
        """, (user_id,))
        result = c.fetchone()
        return result[0] if result else 0
    
    @staticmethod
    def get_chat_partners(user_id):
        """チャット相手一覧を取得"""
        db = Message.get_db()
        c = db.cursor()
        c.execute("""
            SELECT DISTINCT 
                CASE WHEN sender_id = ? THEN recipient_id ELSE sender_id END as partner_id,
                COUNT(CASE WHEN recipient_id = ? AND is_read = 0 THEN 1 END) as unread_count
            FROM messages 
            WHERE sender_id = ? OR recipient_id = ?
            GROUP BY partner_id
        """, (user_id, user_id, user_id, user_id))
        return c.fetchall()
    
    @staticmethod
    def get_unread_count_from_user(recipient_id, sender_id):
        """特定ユーザーからの未読メッセージ数を取得"""
        db = Message.get_db()
        c = db.cursor()
        c.execute("""
            SELECT COUNT(*) FROM messages 
            WHERE recipient_id = ? AND sender_id = ? AND is_read = 0
        """, (recipient_id, sender_id))
        result = c.fetchone()
        return result[0] if result else 0

class MailSettings(BaseModel):
    """メール設定モデル"""
    
    @staticmethod
    def get():
        """メール設定を取得"""
        db = MailSettings.get_db()
        c = db.cursor()
        c.execute("""
            SELECT server, port, username, password, use_tls, subject_template, body_template
            FROM mail_settings WHERE id = 1
        """)
        return c.fetchone()
    
    @staticmethod
    def update(server, port, username, password, use_tls, subject_template, body_template):
        """メール設定を更新"""
        db = MailSettings.get_db()
        c = db.cursor()
        c.execute("""
            INSERT OR REPLACE INTO mail_settings 
            (id, server, port, username, password, use_tls, subject_template, body_template)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        """, (server, port, username, password, int(use_tls), subject_template, body_template))
        db.commit()

class AdminManagedUsers(BaseModel):
    """管理者-ユーザー関係モデル"""
    
    @staticmethod
    def add_managed_user(admin_id, user_id):
        """管理対象ユーザーを追加"""
        db = AdminManagedUsers.get_db()
        c = db.cursor()
        c.execute("""
            INSERT OR IGNORE INTO admin_managed_users (admin_id, user_id)
            VALUES (?, ?)
        """, (admin_id, user_id))
        db.commit()
    
    @staticmethod
    def remove_managed_user(admin_id, user_id):
        """管理対象ユーザーを削除"""
        db = AdminManagedUsers.get_db()
        c = db.cursor()
        c.execute("""
            DELETE FROM admin_managed_users 
            WHERE admin_id = ? AND user_id = ?
        """, (admin_id, user_id))
        db.commit()
    
    @staticmethod
    def is_managed_by(admin_id, user_id):
        """ユーザーが管理対象かチェック"""
        db = AdminManagedUsers.get_db()
        c = db.cursor()
        c.execute("""
            SELECT 1 FROM admin_managed_users 
            WHERE admin_id = ? AND user_id = ?
        """, (admin_id, user_id))
        return c.fetchone() is not None