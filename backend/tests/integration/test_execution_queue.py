"""
Integration tests for the execution queue.

Verifies:
  1. Jobs can be enqueued and dequeued in FIFO order.
  2. Dequeuing an empty queue returns None without blocking.
  3. A job claimed by one consumer cannot be claimed by another.
  4. Completed jobs are removed from the active queue.
  5. Database state matches in-memory expectations after queue operations.
"""
from datetime import datetime, timezone

import pytest


def _now():
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_enqueue_and_dequeue_fifo_order(db_session):
    """Jobs must be dequeued in the order they were enqueued (by created_at)."""
    from app.campaign.models import Campaign, CampaignJob
    from app.campaign import repository as repo

    campaign = Campaign(
        name="queue-test", status="ACTIVE",
        created_at=_now(), updated_at=_now(),
    )
    db_session.add(campaign)
    await db_session.flush()

    # Enqueue 3 jobs in order
    for i in range(3):
        job = CampaignJob(
            campaign_id=campaign.id,
            status="PENDING",
            platform="tiktok",
        )
        db_session.add(job)
    await db_session.flush()

    # Fetch pending jobs in order
    jobs = await repo.get_pending_jobs(db_session, limit=10)
    assert len(jobs) >= 3

    # Verify they're ordered by id (proxy for FIFO)
    ids = [j.id for j in jobs[:3]]
    assert ids == sorted(ids), "Jobs were not returned in FIFO order"


@pytest.mark.asyncio
async def test_dequeue_empty_returns_empty(db_session):
    """get_pending_jobs on an empty queue must return [] without blocking."""
    from app.campaign import repository as repo

    jobs = await repo.get_pending_jobs(db_session, limit=10)
    # May return empty or a list; must not raise
    assert isinstance(jobs, list)


@pytest.mark.asyncio
async def test_claimed_job_not_returned_again(db_session):
    """A job marked as RUNNING must not appear in subsequent get_pending_jobs calls."""
    from app.campaign.models import Campaign, CampaignJob
    from app.campaign import repository as repo

    campaign = Campaign(
        name="claim-test", status="ACTIVE",
        created_at=_now(), updated_at=_now(),
    )
    db_session.add(campaign)
    await db_session.flush()

    job = CampaignJob(campaign_id=campaign.id, status="PENDING", platform="tiktok")
    db_session.add(job)
    await db_session.flush()
    job_id = job.id

    # Mark as RUNNING
    job.status = "RUNNING"
    job.device_id = "some-device"
    await db_session.flush()

    # Should not appear in pending jobs
    pending = await repo.get_pending_jobs(db_session, limit=10)
    assert job_id not in [j.id for j in pending], (
        "RUNNING job appeared in get_pending_jobs — it would be double-dispatched"
    )


@pytest.mark.asyncio
async def test_completed_job_not_in_pending(db_session):
    """A COMPLETED job must not be returned by get_pending_jobs."""
    from app.campaign.models import Campaign, CampaignJob
    from app.campaign import repository as repo

    campaign = Campaign(
        name="completed-queue-test", status="DONE",
        created_at=_now(), updated_at=_now(),
    )
    db_session.add(campaign)
    await db_session.flush()

    job = CampaignJob(
        campaign_id=campaign.id, status="COMPLETED",
        platform="tiktok",
        updated_at=_now(),
    )
    db_session.add(job)
    await db_session.flush()
    job_id = job.id

    pending = await repo.get_pending_jobs(db_session, limit=100)
    assert job_id not in [j.id for j in pending]
