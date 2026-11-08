"""
Shared pytest fixtures for MirrorHub backend tests.

Key decisions
-------------
* Uses in-memory SQLite (never touches mirrorhub.db)
* StaticPool ensures every async operation hits the same in-memory instance
* PRAGMA foreign_keys=ON is set on every connection — mirrors production
* device_session._active is reset before/after every test (module-level state)
* OpenAI client is monkey-patched at session scope so tests never make real calls
"""
import asyncio
import os
import tempfile

# ADR-005: tests must never touch the real %APPDATA%\Mirrorhub. Set before app imports.
os.environ.setdefault("MIRRORHUB_DATA_DIR", tempfile.mkdtemp(prefix="mirrorhub-test-"))

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.database import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ── Database fixtures ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def db_engine() -> AsyncEngine:
    """
    In-memory SQLite engine with:
      - StaticPool (all connections share the same in-memory DB instance)
      - PRAGMA foreign_keys=ON (matches production database.py)
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine: AsyncEngine) -> AsyncSession:
    """A single AsyncSession for one test function, backed by the in-memory DB."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ── Module-level state reset ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_device_session():
    """
    Clear device_session._active before and after every test.

    device_session uses a module-level dict so its state leaks between tests
    unless we reset it explicitly here.
    """
    from app.execution import device_session
    device_session._active.clear()
    yield
    device_session._active.clear()


# ── AI / OpenAI mock ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def mock_openai():
    """
    Prevent any test from accidentally calling the real OpenAI API.

    Patches openai.AsyncOpenAI so all AI-related code gets a fake client
    that returns configurable responses.
    """
    fake_client = MagicMock()
    fake_completion = MagicMock()
    fake_completion.choices = [
        MagicMock(message=MagicMock(content='{"status": "ok", "result": "mocked"}'))
    ]
    fake_client.chat.completions.create = AsyncMock(return_value=fake_completion)

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        yield fake_client


# ── ADB / scrcpy mock ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_adb_connect(monkeypatch):
    """
    Mock the adb_connect call in scrcpy service to return success immediately
    without spawning real processes.
    """
    async def _fake_connect(adb_address: str):
        return True, f"connected to {adb_address}"

    monkeypatch.setattr(
        "app.services.scrcpy.adb_connect", _fake_connect
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"
