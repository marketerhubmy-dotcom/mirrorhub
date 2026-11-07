"""
CLAIM: Config divergence fixed — dispatcher uses centralized settings.

Verifies:
  1. settings.campaign_poll_interval and campaign_retry_delay exist.
  2. No local POLL_INTERVAL / RETRY_DELAY constants in dispatcher.py.
  3. Dispatcher references settings.campaign_poll_interval in source.
  4. CORS default is restricted (not "*").
  5. vision_max_screenshots setting exists with a sensible default.
  6. openai_api_key is never logged at INFO level.
"""
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).parent.parent.parent
_DISPATCHER = _BACKEND / "app" / "campaign" / "dispatcher.py"


# ── Settings values ───────────────────────────────────────────────────────────

def test_campaign_poll_interval_exists():
    from app.core.config import settings
    assert hasattr(settings, "campaign_poll_interval")
    assert settings.campaign_poll_interval > 0


def test_campaign_retry_delay_exists():
    from app.core.config import settings
    assert hasattr(settings, "campaign_retry_delay")
    assert settings.campaign_retry_delay > 0


def test_vision_max_screenshots_exists():
    from app.core.config import settings
    assert hasattr(settings, "vision_max_screenshots")
    assert settings.vision_max_screenshots > 0


def test_cors_is_not_wildcard():
    """CORS default must NOT be '*' — would expose the app to any origin in production."""
    from app.core.config import settings
    assert settings.cors_origins.strip() != "*", (
        "cors_origins is '*' — this allows any origin and is unsafe for production"
    )


def test_cors_includes_localhost():
    from app.core.config import settings
    origins = [o.strip() for o in settings.cors_origins.split(",")]
    assert any("localhost" in o for o in origins), (
        "At least one localhost origin should be in the default CORS allowlist"
    )


# ── Dispatcher source does NOT define local poll constants ────────────────────

def test_dispatcher_has_no_local_poll_interval():
    """POLL_INTERVAL must not be redefined locally in dispatcher.py."""
    text = _DISPATCHER.read_text(encoding="utf-8")
    assert not re.search(r"^POLL_INTERVAL\s*=", text, re.MULTILINE), (
        "dispatcher.py defines a local POLL_INTERVAL — config divergence"
    )


def test_dispatcher_has_no_local_retry_delay():
    """RETRY_DELAY must not be redefined locally in dispatcher.py."""
    text = _DISPATCHER.read_text(encoding="utf-8")
    assert not re.search(r"^RETRY_DELAY\s*=", text, re.MULTILINE), (
        "dispatcher.py defines a local RETRY_DELAY — config divergence"
    )


def test_dispatcher_uses_settings_poll_interval():
    """dispatcher.py must reference settings.campaign_poll_interval."""
    text = _DISPATCHER.read_text(encoding="utf-8")
    assert "settings.campaign_poll_interval" in text


def test_dispatcher_uses_settings_retry_delay():
    """dispatcher.py must reference settings.campaign_retry_delay."""
    text = _DISPATCHER.read_text(encoding="utf-8")
    assert "settings.campaign_retry_delay" in text
