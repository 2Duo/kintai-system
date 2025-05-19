-- ユーザーテーブル
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    overtime_threshold TEXT DEFAULT '18:00'
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
