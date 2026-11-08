"""Agent memory — rewritten against `app.agents.memory` (remember/recall_one/forget)."""
import pytest

from app.agents import memory


@pytest.mark.asyncio
async def test_remember_and_recall_roundtrip(db_session):
    await memory.remember(db_session, "k1", "device", {"data": 42}, summary="s")
    e = await memory.recall_one(db_session, "k1")
    assert e is not None and e.category == "device" and '"data": 42' in e.value_json


@pytest.mark.asyncio
async def test_remember_upserts_same_key(db_session):
    await memory.remember(db_session, "k", "device", {"v": 1})
    await memory.remember(db_session, "k", "device", {"v": 2})
    all_ = await memory.recall_all(db_session)
    assert len(all_) == 1 and '"v": 2' in all_[0].value_json


@pytest.mark.asyncio
async def test_category_filter_isolates_entries(db_session):
    await memory.remember(db_session, "a", "cat-A", {"o": "A"})
    await memory.remember(db_session, "b", "cat-B", {"o": "B"})
    assert [e.key for e in await memory.recall_all(db_session, "cat-A")] == ["a"]
    assert [e.key for e in await memory.recall_all(db_session, "cat-B")] == ["b"]


@pytest.mark.asyncio
async def test_recall_missing_returns_none(db_session):
    assert await memory.recall_one(db_session, "ghost") is None


@pytest.mark.asyncio
async def test_forget(db_session):
    await memory.remember(db_session, "x", "c", {})
    assert await memory.forget(db_session, "x") is True
    assert await memory.recall_one(db_session, "x") is None
    assert await memory.forget(db_session, "x") is False
