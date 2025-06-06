import os, io, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("SECRET_KEY", "test-secret")
from app import app


def test_large_csv_rejected():
    app.config['TESTING'] = True
    app.config['MAX_CONTENT_LENGTH'] = 100
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['_csrf_token'] = 'token'
        data = {
            'file': (io.BytesIO(b'a' * 101), 'test.csv'),
            '_csrf_token': 'token'
        }
        resp = client.post('/my/import', data=data, content_type='multipart/form-data')
        assert resp.status_code == 413
