"""
CLAIM: datetime.utcnow() has been eliminated from all application code.

Verifies by static analysis (AST + regex):
  1. No Python file under app/ calls datetime.utcnow().
  2. No Python file under app/ uses default=datetime.utcnow (bare reference).
  3. No Python file under app/ uses onupdate=datetime.utcnow (bare reference).
  4. New timestamps in model defaults use lambda: datetime.now(timezone.utc).

These are Python 3.12 deprecation items that will become TypeErrors in 3.13.
"""
import ast
import re
from pathlib import Path

import pytest

_APP = Path(__file__).parent.parent.parent / "app"


def _source_files():
    return list(_APP.rglob("*.py"))


# ── No .utcnow() calls ────────────────────────────────────────────────────────

def test_no_utcnow_calls():
    """
    datetime.utcnow() must not appear anywhere in app source.

    Fails with a list of every offending file + line.
    """
    violations: list[str] = []
    pattern = re.compile(r"datetime\.utcnow\s*\(\s*\)")

    for py_file in _source_files():
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                rel = py_file.relative_to(_APP.parent)
                violations.append(f"  {rel}:{lineno}  {line.strip()}")

    assert not violations, (
        "Found datetime.utcnow() calls:\n" + "\n".join(violations)
    )


# ── No bare datetime.utcnow references (column defaults) ─────────────────────

def test_no_bare_utcnow_default():
    """
    default=datetime.utcnow (without calling it) must not appear in any model.

    SQLAlchemy evaluates the bare callable at INSERT time — this is the Python
    3.12 deprecation path that produces DeprecationWarning today and TypeError in 3.13.
    """
    violations: list[str] = []
    pattern = re.compile(r"default\s*=\s*datetime\.utcnow\b(?!\s*\()")

    for py_file in _source_files():
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                rel = py_file.relative_to(_APP.parent)
                violations.append(f"  {rel}:{lineno}  {line.strip()}")

    assert not violations, (
        "Found bare default=datetime.utcnow:\n" + "\n".join(violations)
    )


def test_no_bare_utcnow_onupdate():
    """onupdate=datetime.utcnow (bare) must not appear in any model."""
    violations: list[str] = []
    pattern = re.compile(r"onupdate\s*=\s*datetime\.utcnow\b(?!\s*\()")

    for py_file in _source_files():
        text = py_file.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                rel = py_file.relative_to(_APP.parent)
                violations.append(f"  {rel}:{lineno}  {line.strip()}")

    assert not violations, (
        "Found bare onupdate=datetime.utcnow:\n" + "\n".join(violations)
    )


# ── Positive: lambda pattern is used instead ─────────────────────────────────

def test_models_use_lambda_utc_default():
    """
    Model files should use lambda: datetime.now(timezone.utc) for defaults.

    Checks that the replacement pattern is present in at least the four
    primary model modules touched by Release 2.1.1.
    """
    model_files = [
        _APP / "campaign" / "models.py",
        _APP / "agents" / "models.py",
        _APP / "execution" / "models.py",
        _APP / "orchestrator" / "models.py",
    ]
    pattern = re.compile(r"lambda\s*:\s*datetime\.now\s*\(\s*timezone\.utc\s*\)")
    for model_file in model_files:
        text = model_file.read_text(encoding="utf-8")
        assert pattern.search(text), (
            f"{model_file.name} does not use lambda: datetime.now(timezone.utc) for column defaults"
        )


# ── New timestamps are timezone-aware ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_campaign_created_at_is_tz_aware(db_session):
    """Newly inserted Campaign rows must have timezone-aware created_at."""
    from app.campaign import repository as repo
    from app.campaign.schemas import CampaignCreate

    c = await repo.create_campaign(db_session, CampaignCreate(name="tz-test"))
    # Re-fetch to ensure the column default ran
    fetched = await repo.get_campaign(db_session, c.id)
    assert fetched is not None
    assert fetched.created_at is not None
    # SQLite stores as TEXT — after retrieval SQLAlchemy may return naive or aware.
    # At minimum confirm no naive comparisons raise TypeError.
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    # If tz-aware, comparison works; if naive (SQLite quirk), at least no exception
    try:
        _ = fetched.created_at < now_utc
    except TypeError:
        pytest.fail(
            "created_at is a naive datetime — cannot compare with timezone-aware datetime"
        )
