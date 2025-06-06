import os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("SECRET_KEY", "test-secret")
import app as app_module
import sqlite3
app = app_module.app

@pytest.fixture
def client(tmp_path):
    app.config['TESTING'] = True

    original_db = app_module.DB_PATH
    test_db = tmp_path / "test.db"
    app_module.DB_PATH = str(test_db)
    app_module.initialize_database()

    conn = sqlite3.connect(app_module.DB_PATH)
    cur = conn.execute(
        "INSERT INTO users (email, name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
        ("dummy@example.com", "Dummy", "hash", 1),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['is_admin'] = True
        yield client

    if os.path.exists(app_module.DB_PATH):
        os.remove(app_module.DB_PATH)
    app_module.DB_PATH = original_db

def test_path_traversal_rejected(client):
    resp = client.get('/exports/../app.py')
    assert resp.status_code == 400
