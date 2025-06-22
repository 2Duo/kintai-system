import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("SECRET_KEY", "test-secret")
from app import calculate_overtime


def test_overtime_with_late_start():
    assert calculate_overtime("22:00", "18:00", "19:00") == "03:00"


def test_overtime_standard():
    assert calculate_overtime("20:30", "18:00", "09:00") == "02:30"


def test_overtime_before_threshold():
    assert calculate_overtime("17:30", "18:00", "09:00") == ""
