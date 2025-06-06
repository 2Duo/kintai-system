import os, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("SECRET_KEY", "test-secret")
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['is_admin'] = True
        yield client

def test_path_traversal_rejected(client):
    resp = client.get('/exports/../app.py')
    assert resp.status_code == 400
