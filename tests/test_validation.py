import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("SECRET_KEY", "test-secret")
import pytest
from app import is_valid_email, is_valid_time

@pytest.mark.parametrize("email", [
    "test@example.com",
    "user.name+tag@domain.co",
])
def test_valid_email(email):
    assert is_valid_email(email)

@pytest.mark.parametrize("email", [
    "invalid",
    "a@b",
    "user@.com",
    "user@domain",
    "@nouser.com",
])
def test_invalid_email(email):
    assert not is_valid_email(email)

@pytest.mark.parametrize("time_str", [
    "00:00",
    "23:59",
    "9:00",
])
def test_valid_time(time_str):
    assert is_valid_time(time_str)

@pytest.mark.parametrize("time_str", [
    "24:00",
    "12:60",
    "abc",
    "99:99",
])
def test_invalid_time(time_str):
    assert not is_valid_time(time_str)
