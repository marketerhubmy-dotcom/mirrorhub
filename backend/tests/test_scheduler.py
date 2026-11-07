"""Tests for the campaign scheduler's recurrence logic."""
import pytest
from datetime import datetime, timedelta, timezone
from app.campaign.scheduler import _compute_next

# All _compute_next results are timezone-aware UTC datetimes (datetime.now(timezone.utc))
_NOW = datetime.now(timezone.utc)


def test_hourly_returns_future():
    expr = {"type": "hourly"}
    result = _compute_next(expr)
    assert result is not None
    assert result.tzinfo is not None, "result must be timezone-aware"
    assert result > datetime.now(timezone.utc)


def test_daily_returns_future():
    expr = {"type": "daily", "time": "09:00"}
    result = _compute_next(expr)
    assert result is not None
    assert result.tzinfo is not None
    assert result > datetime.now(timezone.utc)
    assert result.hour == 9
    assert result.minute == 0


def test_weekly_monday():
    expr = {"type": "weekly", "day": "monday", "time": "08:30"}
    result = _compute_next(expr)
    assert result is not None
    assert result.tzinfo is not None
    assert result.weekday() == 0  # Monday
    assert result.hour == 8
    assert result.minute == 30


def test_weekly_friday():
    expr = {"type": "weekly", "day": "friday", "time": "12:00"}
    result = _compute_next(expr)
    assert result is not None
    assert result.tzinfo is not None
    assert result.weekday() == 4  # Friday


def test_monthly_day_1():
    expr = {"type": "monthly", "day": 1, "time": "00:00"}
    result = _compute_next(expr)
    assert result is not None
    assert result.tzinfo is not None
    assert result.day == 1
    assert result > datetime.now(timezone.utc)


def test_unknown_type_returns_none():
    expr = {"type": "decade"}
    result = _compute_next(expr)
    assert result is None


def test_hourly_is_approximately_one_hour_away():
    before = datetime.now(timezone.utc)
    result = _compute_next({"type": "hourly"})
    after = datetime.now(timezone.utc)
    assert result.tzinfo is not None
    assert result >= before + timedelta(minutes=59)
    assert result <= after + timedelta(hours=1, seconds=5)
