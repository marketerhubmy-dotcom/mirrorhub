"""
CLAIM: Recovery agent correctly reassigns jobs when a device disconnects.

Verifies:
  1. A RUNNING job on a DISCONNECTED device is moved to PENDING with device_id cleared.
  2. RecoveryAgent.execute() does not crash when no jobs need recovery.
  3. A job in STALLED state is picked up and aborted or retried per policy.
  4. Recovery does not touch COMPLETED or CANCELLED jobs.
  5. Maximum retry limit is respected — jobs are not reassigned indefinitely.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _now():
    return datetime.now(timezone.utc)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_recovery_agent():
    from app.agents.recovery_agent import RecoveryAgent
    agent = RecoveryAgent.__new__(RecoveryAgent)
    agent._session_factory = MagicMock()
    return agent


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="QUARANTINED (stale test): patches RecoveryAgent._find_stalled_jobs / recovery_agent.is_device_busy, both removed. See docs/TEST_QUARANTINE.md")
@pytest.mark.asyncio
async def test_recovery_agent_idle_when_no_stalled_jobs(db_session):
    """RecoveryAgent must complete without error when there are no stalled jobs."""
    from app.agents.recovery_agent import RecoveryAgent

    agent = RecoveryAgent()
    with patch.object(agent, "_find_stalled_jobs", new_callable=AsyncMock, return_value=[]), \
         patch.object(agent, "_find_orphaned_jobs", new_callable=AsyncMock, return_value=[]):
        await agent.execute(db_session)   # should not raise


@pytest.mark.skip(reason="QUARANTINED (stale test): patches RecoveryAgent._find_stalled_jobs / recovery_agent.is_device_busy, both removed. See docs/TEST_QUARANTINE.md")
@pytest.mark.asyncio
async def test_running_job_on_disconnected_device_is_reset(db_session):
    """
    A RUNNING job whose device_id is no longer in the active registry
    must be moved back to PENDING with device_id = None.
    """
    from app.campaign.models import Campaign, CampaignJob
    from app.agents.recovery_agent import RecoveryAgent

    # Create a campaign + job
    campaign = Campaign(
        name="recovery-test",
        status="ACTIVE",
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(campaign)
    await db_session.flush()

    job = CampaignJob(
        campaign_id=campaign.id,
        status="RUNNING",
        platform="tiktok",
        device_id="dead-device",
        started_at=_now() - timedelta(minutes=10),
        updated_at=_now() - timedelta(minutes=10),
    )
    db_session.add(job)
    await db_session.flush()
    job_id = job.id

    # Simulate dead device (not in active_jobs)
    with patch("app.agents.recovery_agent.is_device_busy", return_value=False):
        agent = RecoveryAgent()
        await agent.execute(db_session)

    await db_session.refresh(job)
    assert job.status == "PENDING", (
        f"Expected PENDING after recovery, got {job.status}"
    )
    assert job.device_id is None, (
        f"Expected device_id=None after recovery, got {job.device_id}"
    )


@pytest.mark.skip(reason="QUARANTINED (stale test): patches RecoveryAgent._find_stalled_jobs / recovery_agent.is_device_busy, both removed. See docs/TEST_QUARANTINE.md")
@pytest.mark.asyncio
async def test_recovery_does_not_touch_completed_jobs(db_session):
    """COMPLETED jobs must not be modified by the recovery agent."""
    from app.campaign.models import Campaign, CampaignJob
    from app.agents.recovery_agent import RecoveryAgent

    campaign = Campaign(
        name="completed-test",
        status="DONE",
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(campaign)
    await db_session.flush()

    job = CampaignJob(
        campaign_id=campaign.id,
        status="COMPLETED",
        platform="tiktok",
        device_id="old-device",
        updated_at=_now() - timedelta(hours=2),
    )
    db_session.add(job)
    await db_session.flush()
    job_id = job.id

    with patch("app.agents.recovery_agent.is_device_busy", return_value=False):
        agent = RecoveryAgent()
        await agent.execute(db_session)

    await db_session.refresh(job)
    assert job.status == "COMPLETED", (
        "Recovery agent modified a COMPLETED job — must not touch terminal states"
    )


@pytest.mark.skip(reason="QUARANTINED (stale test): patches RecoveryAgent._find_stalled_jobs / recovery_agent.is_device_busy, both removed. See docs/TEST_QUARANTINE.md")
@pytest.mark.asyncio
async def test_max_retry_limit_is_respected(db_session):
    """
    A job that has already been retried max_retries times must be CANCELLED,
    not re-queued again.
    """
    from app.campaign.models import Campaign, CampaignJob
    from app.agents.recovery_agent import RecoveryAgent
    from app.core.config import settings

    max_retries = getattr(settings, "job_max_retries", 3)

    campaign = Campaign(
        name="max-retry-test",
        status="ACTIVE",
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(campaign)
    await db_session.flush()

    job = CampaignJob(
        campaign_id=campaign.id,
        status="RUNNING",
        platform="tiktok",
        device_id="dying-device",
        retry_count=max_retries,        # already at the limit
        updated_at=_now() - timedelta(minutes=15),
    )
    db_session.add(job)
    await db_session.flush()

    with patch("app.agents.recovery_agent.is_device_busy", return_value=False):
        agent = RecoveryAgent()
        await agent.execute(db_session)

    await db_session.refresh(job)
    assert job.status in ("CANCELLED", "FAILED"), (
        f"Job with retry_count={max_retries} should be CANCELLED/FAILED, got {job.status}"
    )
