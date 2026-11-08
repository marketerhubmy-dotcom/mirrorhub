"""
Execution queue (campaign repository) — rewritten against the current API.

The original file called `get_pending_jobs`, which no longer exists. The queue is
now `ExecutionQueue` rows managed by `enqueue / list_active_queue /
update_queue_entry_status`.
"""
import pytest

from app.campaign import repository as repo
from app.campaign.models import Campaign, CampaignJob


async def _job(db):
    c = Campaign(name="q")
    db.add(c)
    await db.flush()
    j = CampaignJob(campaign_id=c.id, platform="tiktok")
    db.add(j)
    await db.flush()
    return j


@pytest.mark.asyncio
async def test_queue_is_ordered_by_queue_order_then_id(db_session):
    a, b, c = [await _job(db_session) for _ in range(3)]
    await repo.enqueue(db_session, a.id, queue_order=2)
    await repo.enqueue(db_session, b.id, queue_order=1)
    await repo.enqueue(db_session, c.id, queue_order=1)
    q = await repo.list_queue(db_session)
    assert [e.campaign_job_id for e in q] == [b.id, c.id, a.id]


@pytest.mark.asyncio
async def test_empty_queue_returns_empty_list(db_session):
    assert await repo.list_queue(db_session) == []
    assert await repo.list_active_queue(db_session) == []


@pytest.mark.asyncio
async def test_running_entry_stays_active_and_gets_started_at(db_session):
    j = await _job(db_session)
    e = await repo.enqueue(db_session, j.id)
    e = await repo.update_queue_entry_status(db_session, e.id, "RUNNING")
    assert e.started_at is not None
    assert [x.id for x in await repo.list_active_queue(db_session)] == [e.id]


@pytest.mark.asyncio
@pytest.mark.parametrize("final", ["COMPLETED", "FAILED", "CANCELLED"])
async def test_finished_entries_leave_active_queue(db_session, final):
    j = await _job(db_session)
    e = await repo.enqueue(db_session, j.id)
    e = await repo.update_queue_entry_status(db_session, e.id, final)
    assert e.finished_at is not None
    assert await repo.list_active_queue(db_session) == []
    assert len(await repo.list_queue(db_session)) == 1  # history kept


@pytest.mark.asyncio
async def test_update_unknown_entry_returns_none(db_session):
    assert await repo.update_queue_entry_status(db_session, 424242, "RUNNING") is None


@pytest.mark.asyncio
async def test_lookup_by_job_returns_latest_entry(db_session):
    j = await _job(db_session)
    await repo.enqueue(db_session, j.id)
    second = await repo.enqueue(db_session, j.id)
    assert (await repo.get_queue_entry_by_job(db_session, j.id)).id == second.id


@pytest.mark.asyncio
async def test_deleting_campaign_removes_its_jobs(db_session):
    j = await _job(db_session)
    cid = j.campaign_id
    await db_session.commit()
    assert await repo.delete_campaign(db_session, cid) is True
    assert await repo.get_campaign_job(db_session, j.id) is None
    assert await repo.delete_campaign(db_session, cid) is False
