"""
Tests for the structured logging utility (app.utils.logging).

Verifies:
  1. get_logger returns a StructuredLogger.
  2. Keyword arguments become structured fields in the log record.
  3. Sensitive keys are redacted (api_key, token, password, etc.).
  4. JSON formatter emits valid JSON with expected fields.
  5. Human formatter includes the message without crashing.
  6. configure_logging is idempotent (safe to call multiple times).
  7. No production secret appears in log output.
"""
import json
import logging
import io

import pytest

from app.utils.logging import (
    get_logger,
    configure_logging,
    reset_logging,
    _redact,
    _JSONFormatter,
    _HumanFormatter,
    StructuredLogger,
)
from app.utils.correlation import set_correlation_id


@pytest.fixture(autouse=True)
def clean_logging():
    """Reset logging configuration before and after each test."""
    reset_logging()
    yield
    reset_logging()


# ── get_logger ────────────────────────────────────────────────────────────────

def test_get_logger_returns_structured_logger():
    log = get_logger("test.module")
    assert isinstance(log, StructuredLogger)


def test_get_logger_name():
    log = get_logger("my.service")
    assert log.logger.name == "my.service"


# ── Redaction ─────────────────────────────────────────────────────────────────

def test_redact_api_key_in_dict():
    data = {"api_key": "sk-super-secret", "device_id": "abc"}
    result = _redact(data)
    assert result["api_key"] == "[REDACTED]"
    assert result["device_id"] == "abc"


def test_redact_token_in_dict():
    data = {"token": "Bearer xyz123"}
    assert _redact(data)["token"] == "[REDACTED]"


def test_redact_password_in_dict():
    data = {"password": "hunter2", "user": "admin"}
    result = _redact(data)
    assert result["password"] == "[REDACTED]"
    assert result["user"] == "admin"


def test_redact_nested_dict():
    data = {"auth": {"secret": "very-secret"}, "name": "test"}
    result = _redact(data)
    assert result["auth"]["secret"] == "[REDACTED]"
    assert result["name"] == "test"


def test_redact_leaves_safe_keys_intact():
    data = {"device_id": "abc", "duration_ms": 50, "status": "OK"}
    result = _redact(data)
    assert result == data


# ── JSON formatter ────────────────────────────────────────────────────────────

def _make_record(msg: str, **extras) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0, msg=msg,
        args=(), exc_info=None,
    )
    record._structured = extras
    return record


def test_json_formatter_produces_valid_json():
    set_correlation_id("test1234")
    formatter = _JSONFormatter()
    record = _make_record("mirror_started", device_id="abc", duration_ms=42)
    output = formatter.format(record)
    parsed = json.loads(output)    # must not raise

    assert parsed["event"] == "mirror_started"
    assert parsed["level"] == "INFO"
    assert parsed["correlation_id"] == "test1234"
    assert parsed["device_id"] == "abc"
    assert parsed["duration_ms"] == 42


def test_json_formatter_redacts_api_key():
    formatter = _JSONFormatter()
    record = _make_record("ai_call", api_key="sk-secret123", campaign_id=5)
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["api_key"] == "[REDACTED]"
    assert parsed["campaign_id"] == 5


# ── Human formatter ───────────────────────────────────────────────────────────

def test_human_formatter_includes_message():
    formatter = _HumanFormatter()
    record = _make_record("test event")
    output = formatter.format(record)
    assert "test event" in output


def test_human_formatter_includes_kv_pairs():
    formatter = _HumanFormatter()
    record = _make_record("job_done", campaign_id=99)
    output = formatter.format(record)
    assert "campaign_id" in output
    assert "99" in output


# ── configure_logging ─────────────────────────────────────────────────────────

def test_configure_logging_is_idempotent():
    """Calling configure_logging twice must not add duplicate handlers."""
    configure_logging(level="DEBUG")
    handlers_after_first = len(logging.getLogger().handlers)
    configure_logging(level="DEBUG")   # second call — should be no-op
    handlers_after_second = len(logging.getLogger().handlers)
    assert handlers_after_first == handlers_after_second


def test_configure_logging_sets_level():
    configure_logging(level="WARNING")
    assert logging.getLogger().level == logging.WARNING
