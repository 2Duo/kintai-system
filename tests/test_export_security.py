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
    original_export = app_module.EXPORT_DIR

    test_db = tmp_path / "test.db"
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    app_module.DB_PATH = str(test_db)
    app_module.EXPORT_DIR = str(export_dir)
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
    app_module.EXPORT_DIR = original_export

def test_path_traversal_rejected(client):
    resp = client.get('/exports/../app.py')
    assert resp.status_code == 400

@pytest.mark.parametrize("name", ["../bad", "user/evil"])
def test_generate_csv_name_sanitization(client, tmp_path, name):
    export_dir = tmp_path / "exports"
    export_dir.mkdir(exist_ok=True)
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.execute(
        "INSERT INTO attendance (user_id, timestamp, type) VALUES (1, '2023-01-01T09:00:00', 'in')"
    )
    conn.execute(
        "INSERT INTO attendance (user_id, timestamp, type) VALUES (1, '2023-01-01T18:00:00', 'out')"
    )
    conn.commit()
    conn.close()
    with app.app_context():
        path = app_module.generate_csv(1, name, 2023, 1, str(export_dir))
    assert os.path.commonpath([str(export_dir), path]) == str(export_dir)
    assert os.path.isfile(path)

def test_symlink_traversal_rejected(client, tmp_path):
    outside = tmp_path / 'outside.csv'
    outside.write_text('secret')
    link = os.path.join(app_module.EXPORT_DIR, 'link.csv')
    os.symlink(outside, link)
    resp = client.get('/exports/link.csv')
    assert resp.status_code == 400