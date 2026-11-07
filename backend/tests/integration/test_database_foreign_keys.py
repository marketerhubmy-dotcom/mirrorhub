"""
CLAIM: PRAGMA foreign_keys=ON is enforced — orphaned rows are rejected at insert.

Verifies:
  1. Inserting a job with a non-existent campaign_id raises IntegrityError.
  2. Inserting a job linked to an existing campaign succeeds.
  3. Deleting a campaign while jobs reference it raises IntegrityError (if CASCADE is off)
     or cascades (if ON DELETE CASCADE) — either is acceptable; what's NOT acceptable
     is silently creating orphaned rows.
  4. PRAGMA foreign_keys=ON applies to the test engine (autouse conftest fixture).
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


@pytest.mark.asyncio
async def test_pragma_foreign_keys_is_on(db_session):
    """Confirm PRAGMA returns 1 (enabled) for the test DB connection."""
    result = await db_session.execute(text("PRAGMA foreign_keys"))
    value = result.scalar()
    assert value == 1, (
        "PRAGMA foreign_keys is OFF — FK enforcement is not active in the test engine"
    )


@pytest.mark.asyncio
async def test_job_rejects_invalid_campaign_fk(db_session):
    """
    Inserting a CampaignJob with a campaign_id that doesn't exist must raise IntegrityError.
    """
    from app.campaign.models import CampaignJob

    orphan_job = CampaignJob(
        campaign_id=999_999,      # no such campaign
        status="PENDING",
        platform="tiktok",
        device_id=None,
    )
    db_session.add(orphan_job)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_job_with_valid_campaign_fk_succeeds(db_session):
    """Inserting a job that references an existing campaign must not raise."""
    from app.campaign.models import Campaign, CampaignJob
    from datetime import datetime, timezone

    campaign = Campaign(
        name="fk-test-campaign",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(campaign)
    await db_session.flush()

    job = CampaignJob(
        campaign_id=campaign.id,
        status="PENDING",
        platform="tiktok",
    )
    db_session.add(job)
    await db_session.flush()   # should not raise


@pytest.mark.asyncio
async def test_campaign_delete_respects_fk_constraint(db_session):
    """
    Deleting a campaign that has jobs must either cascade (OK) or raise IntegrityError (OK).
    It must NEVER silently succeed while leaving orphaned jobs.
    """
    from app.campaign.models import Campaign, CampaignJob
    from datetime import datetime, timezone

    campaign = Campaign(
        name="delete-test",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(campaign)
    await db_session.flush()

    job = CampaignJob(campaign_id=campaign.id, status="PENDING", platform="tiktok")
    db_session.add(job)
    await db_session.flush()

    job_id = job.id
    campaign_id = campaign.id

    try:
        await db_session.delete(campaign)
        await db_session.flush()
        # If we get here, cascade deleted the job — verify no orphan remains
        from sqlalchemy import select
        from app.campaign.models import CampaignJob as J
        result = await db_session.execute(
            select(J).where(J.id == job_id)
        )
        orphan = result.scalar_one_or_none()
        assert orphan is None, (
            f"Campaign was deleted but job {job_id} still exists (orphaned row)"
        )
    except IntegrityError:
        # FK constraint blocked the delete — this is also correct behaviour
        await db_session.rollback()
