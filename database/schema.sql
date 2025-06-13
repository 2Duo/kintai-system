-- ユーザーテーブル
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    is_superadmin INTEGER DEFAULT 0,        -- ★スーパー管理者フラグ追加
    overtime_threshold TEXT DEFAULT '18:00'
);

-- 管理下にするユーザー
CREATE TABLE IF NOT EXISTS admin_managed_users (
    admin_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (admin_id, user_id),
    FOREIGN KEY (admin_id) REFERENCES users(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 勤怠記録テーブル
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    type TEXT CHECK(type IN ('in', 'out')) NOT NULL,
    description TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- メール設定（常に1行のみ）
CREATE TABLE IF NOT EXISTS mail_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    server TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT,
    password TEXT,
    use_tls INTEGER DEFAULT 1,
    subject_template TEXT,
    body_template TEXT
);

-- チャットメッセージ
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(recipient_id) REFERENCES users(id) ON DELETE CASCADE
);
