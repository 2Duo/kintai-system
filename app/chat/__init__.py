from flask import Blueprint, render_template, request, session, Response, stream_with_context, jsonify
from collections import defaultdict
from weakref import WeakSet
import json
from datetime import datetime
from ..auth import login_required, admin_required, check_csrf
from ..models import User, Message, AdminManagedUsers
from ..utils.audit import log_audit_event

try:
    from gevent.queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty

chat_bp = Blueprint('chat', __name__)

# SSE用のグローバル変数
user_streams = defaultdict(WeakSet)

def can_chat(user_id, partner_id):
    """チャット権限をチェック"""
    user = User.get_by_id(user_id)
    partner = User.get_by_id(partner_id)
    
    if not user or not partner:
        return False
    
    # スーパー管理者は誰とでもチャット可能
    if user['is_superadmin']:
        return True
    
    # 管理者の場合、管理対象ユーザーとのみチャット可能
    if user['is_admin']:
        return AdminManagedUsers.is_managed_by(user_id, partner_id)
    
    # 一般ユーザーの場合、自分を管理する管理者とのみチャット可能
    return AdminManagedUsers.is_managed_by(partner_id, user_id)

@chat_bp.route('/chat')
@login_required
def my_chat():
    """チャット一覧画面"""
    user_id = session['user_id']
    is_admin = session.get('is_admin', False)
    is_superadmin = session.get('is_superadmin', False)
    
    # チャット相手一覧を取得
    chat_partners = []
    
    if is_superadmin:
        # スーパー管理者は全ユーザーとチャット可能
        all_users = User.get_all()
        for user in all_users:
            if user['id'] != user_id:  # 自分以外
                unread_count = Message.get_unread_count_from_user(user_id, user['id'])
                chat_partners.append({
                    'id': user['id'],
                    'name': user['name'],
                    'unread_count': unread_count
                })
    elif is_admin:
        # 管理者は管理対象ユーザーとチャット可能
        managed_users = User.get_managed_users(user_id)
        for user in managed_users:
            unread_count = Message.get_unread_count_from_user(user_id, user['id'])
            chat_partners.append({
                'id': user['id'],
                'name': user['name'],
                'unread_count': unread_count
            })
    else:
        # 一般ユーザーは自分を管理する管理者とチャット可能
        # まず自分を管理する管理者を見つける
        db = Message.get_db()
        c = db.cursor()
        c.execute("""
            SELECT u.id, u.name FROM users u
            INNER JOIN admin_managed_users m ON u.id = m.admin_id
            WHERE m.user_id = ? AND (u.is_admin = 1 OR u.is_superadmin = 1)
        """, (user_id,))
        
        admins = c.fetchall()
        for admin in admins:
            unread_count = Message.get_unread_count_from_user(user_id, admin['id'])
            chat_partners.append({
                'id': admin['id'],
                'name': admin['name'],
                'unread_count': unread_count
            })
    
    return render_template('chat_list.html', chat_partners=chat_partners)

@chat_bp.route('/chat/<int:partner_id>')
@login_required
def chat_with_user(partner_id):
    """特定ユーザーとのチャット画面"""
    user_id = session['user_id']
    
    # チャット権限をチェック
    if not can_chat(user_id, partner_id):
        return "アクセス拒否", 403
    
    partner = User.get_by_id(partner_id)
    if not partner:
        return "ユーザーが見つかりません", 404
    
    # メッセージ履歴を取得
    messages = Message.get_conversation(user_id, partner_id)
    
    # メッセージを既読にする
    Message.mark_as_read(user_id, partner_id)
    
    return render_template('chat.html', 
                         partner=partner, 
                         messages=messages,
                         current_user_id=user_id)

@chat_bp.route('/send_message', methods=['POST'])
@login_required
def send_message():
    """メッセージ送信"""
    if not check_csrf():
        return jsonify({'success': False, 'error': 'CSRF token error'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    partner_id = data.get('partner_id')
    message = data.get('message', '').strip()
    
    if not partner_id or not message:
        return jsonify({'success': False, 'error': 'Invalid data'}), 400
    
    user_id = session['user_id']
    
    # チャット権限をチェック
    if not can_chat(user_id, partner_id):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    # メッセージ長度チェック
    if len(message) > 1000:
        return jsonify({'success': False, 'error': 'Message too long'}), 400
    
    # HTMLエスケープ
    import html
    message = html.escape(message)
    
    try:
        # メッセージを保存
        message_id = Message.create(user_id, partner_id, message)
        
        # SSE経由で相手に通知
        notify_user(partner_id, {
            'type': 'new_message',
            'sender_id': user_id,
            'sender_name': session['user_name'],
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
        
        log_audit_event("message_sent", user_id, session['user_name'])
        
        return jsonify({'success': True, 'message_id': message_id})
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to send message'}), 500

@chat_bp.route('/events')
@login_required
def events():
    """SSE エンドポイント"""
    user_id = session['user_id']
    
    def stream():
        q = Queue()
        user_streams[user_id].add(q)
        
        try:
            # Chrome の buffering 問題を回避するためのパディング
            yield "data: " + " " * 2048 + "\n\n"
            
            while True:
                try:
                    data = q.get(timeout=30)  # 30秒でタイムアウト
                    yield f"data: {json.dumps(data)}\n\n"
                except Empty:
                    # ハートビート
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
                except Exception:
                    break
        finally:
            # クリーンアップ
            try:
                user_streams[user_id].discard(q)
            except:
                pass
    
    return Response(stream_with_context(stream()), 
                   mimetype='text/event-stream',
                   headers={
                       'Cache-Control': 'no-cache',
                       'Connection': 'keep-alive',
                       'Access-Control-Allow-Origin': '*'
                   })

def notify_user(user_id, data):
    """特定ユーザーにSSE経由で通知"""
    if user_id in user_streams:
        # WeakSetの要素をコピーしてから反復処理
        streams = list(user_streams[user_id])
        for q in streams:
            try:
                q.put_nowait(data)
            except:
                # 無効なストリームを削除
                try:
                    user_streams[user_id].discard(q)
                except:
                    pass

@chat_bp.route('/unread_count_api')
@login_required
def unread_count_api():
    """未読メッセージ数API"""
    user_id = session['user_id']
    unread_count = Message.get_unread_count(user_id)
    return jsonify({'unread_count': unread_count})

@chat_bp.route('/mark_read', methods=['POST'])
@login_required
def mark_read():
    """メッセージ既読API"""
    if not check_csrf():
        return jsonify({'success': False, 'error': 'CSRF token error'}), 400
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    partner_id = data.get('partner_id')
    if not partner_id:
        return jsonify({'success': False, 'error': 'Invalid data'}), 400
    
    user_id = session['user_id']
    
    # チャット権限をチェック
    if not can_chat(user_id, partner_id):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        Message.mark_as_read(user_id, partner_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to mark as read'}), 500