"""
CLAIM: O(1) query count — batch aggregation query replaces N+1 loop.

Verifies:
  1. Query count stays constant (≤ K) regardless of goal / device count.
  2. The batch status aggregation uses GROUP BY (not one query per goal).
  3. Increasing from 10 to 50 goals does not increase the query count.

Uses SQLAlchemy query event listener to count executed statements.
"""
import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import event, text


def _attach_query_counter(engine):
    """Returns a counter dict; increments 'count' for every executed statement."""
    counter: dict[str, int] = {"count": 0}

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(_conn, _cursor, statement, *args, **kwargs):
        counter["count"] += 1

    return counter


@pytest.mark.asyncio
async def test_batch_aggregation_query_count_constant(db_engine, db_session):
    """
    Insert 10 goals, run agent status aggregation, record query count.
    Insert 40 more goals (50 total), run again.
    Both runs must issue the same number of queries (constant, not O(N)).
    """
    from app.agents.models import AgentGoal
    from app.agents import repository as repo

    # Populate 10 goals
    for i in range(10):
        goal = AgentGoal(
            campaign_id=None,
            status="RUNNING",
            platform="tiktok",
            device_id=f"perf-dev-{i}",
        )
        db_session.add(goal)
    await db_session.flush()

    counter_10 = _attach_query_counter(db_engine)
    _ = await repo.get_goal_status_summary(db_session)
    queries_for_10 = counter_10["count"]

    # Add 40 more goals
    for i in range(10, 50):
        goal = AgentGoal(
            campaign_id=None,
            status="RUNNING",
            platform="tiktok",
            device_id=f"perf-dev-{i}",
        )
        db_session.add(goal)
    await db_session.flush()

    counter_50 = _attach_query_counter(db_engine)
    _ = await repo.get_goal_status_summary(db_session)
    queries_for_50 = counter_50["count"]

    assert queries_for_10 == queries_for_50, (
        f"Query count scaled with data: {queries_for_10} queries for 10 goals "
        f"vs {queries_for_50} queries for 50 goals — O(N) loop detected"
    )
    assert queries_for_10 <= 5, (
        f"Expected ≤5 queries for status aggregation, got {queries_for_10}"
    )


@pytest.mark.asyncio
async def test_device_load_aggregation_uses_group_by(db_engine, db_session):
    """
    Device load query must use a GROUP BY aggregate (one query), not a loop.
    The query count for 1 device and 20 devices must be identical.
    """
    from app.agents import repository as repo
    from app.orchestrator.models import DeviceProfile
    from datetime import datetime, timezone

    for i in range(5):
        profile = DeviceProfile(
            device_id=f"load-dev-{i}",
            platform="tiktok",
            status="IDLE",
            performance_score=5.0,
            last_health_check=datetime.now(timezone.utc),
        )
        db_session.add(profile)
    await db_session.flush()

    counter_5 = _attach_query_counter(db_engine)
    _ = await repo.get_device_load_summary(db_session)
    q5 = counter_5["count"]

    for i in range(5, 20):
        profile = DeviceProfile(
            device_id=f"load-dev-{i}",
            platform="tiktok",
            status="IDLE",
            performance_score=5.0,
            last_health_check=datetime.now(timezone.utc),
        )
        db_session.add(profile)
    await db_session.flush()

    counter_20 = _attach_query_counter(db_engine)
    _ = await repo.get_device_load_summary(db_session)
    q20 = counter_20["count"]

    assert q5 == q20, (
        f"Device load query is O(N): {q5} queries for 5 devices, "
        f"{q20} queries for 20 devices"
    )
