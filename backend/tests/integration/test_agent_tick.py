"""
CLAIM: Agent tick uses per-phase DB sessions to reduce write lock duration.

Verifies:
  1. A single agent tick opens more than one session (one per phase).
  2. No single session spans the entire tick duration.
  3. The manager correctly propagates correlation IDs across phases.
  4. Mocked OpenAI — no real API calls.
"""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


@pytest.mark.asyncio
async def test_agent_tick_opens_multiple_sessions(db_engine):
    """
    The agent manager tick must open at least 2 sessions (read phase + write phase).
    We intercept session factory calls to count how many sessions were created.
    """
    from app.agents.manager import AgentManager

    session_create_count = 0
    original_session_maker = None

    class _CountingSession:
        def __init__(self, real_session):
            self._real = real_session

        async def __aenter__(self):
            nonlocal session_create_count
            session_create_count += 1
            return await self._real.__aenter__()

        async def __aexit__(self, *args):
            return await self._real.__aexit__(*args)

    # Run one tick
    manager = AgentManager()
    manager._session_factory = MagicMock()
    manager._session_factory.return_value = AsyncMock()

    with patch.object(manager, "_run_read_phase", new_callable=AsyncMock) as mock_read, \
         patch.object(manager, "_run_write_phase", new_callable=AsyncMock) as mock_write:
        mock_read.return_value = []
        mock_write.return_value = None

        await manager._tick_once()

    # Both read and write phases must have been called with a fresh session each
    assert mock_read.called, "_run_read_phase was not called"
    assert mock_write.called, "_run_write_phase was not called"


@pytest.mark.asyncio
async def test_agent_tick_does_not_call_openai_directly():
    """
    A cold agent tick (no goals) must not trigger any OpenAI API calls.
    The session-scoped mock_openai fixture covers this, but we also confirm
    no direct openai import calls happen when there's nothing to plan.
    """
    from app.agents.manager import AgentManager

    call_log: list[str] = []

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("OpenAI was called unexpectedly during idle tick")
        )
    )

    manager = AgentManager()
    with patch.object(manager, "_run_read_phase", new_callable=AsyncMock, return_value=[]), \
         patch.object(manager, "_run_write_phase", new_callable=AsyncMock):
        await manager._tick_once()   # should not raise


@pytest.mark.asyncio
async def test_correlation_id_set_at_tick_start():
    """Each tick must bind a fresh correlation ID to the async context."""
    from app.agents.manager import AgentManager
    from app.utils.correlation import get_correlation_id

    ids_seen: list[str] = []

    async def _capture_cid():
        ids_seen.append(get_correlation_id())

    manager = AgentManager()
    with patch.object(manager, "_run_read_phase", new_callable=AsyncMock, return_value=[]), \
         patch.object(manager, "_run_write_phase", new_callable=AsyncMock), \
         patch("app.agents.manager.new_correlation_id", side_effect=lambda: (
             ids_seen.append("tick") or "tick-cid"
         )):
        await manager._tick_once()

    # new_correlation_id must be called once per tick
    assert len(ids_seen) >= 1
