import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("SECRET_KEY", "test-secret")
from flask import session
from app import app, check_csrf


def test_csrf_valid_token():
    with app.test_request_context('/', method='POST', data={'_csrf_token': 'token'}):
        session['_csrf_token'] = 'token'
        assert check_csrf()


def test_csrf_invalid_token():
    with app.test_request_context('/', method='POST', data={'_csrf_token': 'bad'}):
        session['_csrf_token'] = 'token'
        assert not check_csrf()
