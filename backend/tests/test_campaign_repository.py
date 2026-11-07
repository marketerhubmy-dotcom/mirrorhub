"""Integration tests for campaign CRUD operations (uses in-memory SQLite)."""
import pytest
import pytest_asyncio

from app.campaign import repository as repo
from app.campaign.schemas import CampaignCreate, CampaignJobCreate


@pytest_asyncio.fixture
async def campaign(db_session):
    data = CampaignCreate(name="Test Campaign", description="Unit test run")
    return await repo.create_campaign(db_session, data)


@pytest.mark.asyncio
async def test_create_campaign(db_session):
    data = CampaignCreate(name="My Campaign", description="desc")
    c = await repo.create_campaign(db_session, data)
    assert c.id is not None
    assert c.name == "My Campaign"
    assert c.status == "DRAFT"


@pytest.mark.asyncio
async def test_get_campaign(db_session, campaign):
    fetched = await repo.get_campaign(db_session, campaign.id)
    assert fetched is not None
    assert fetched.id == campaign.id


@pytest.mark.asyncio
async def test_list_campaigns(db_session):
    await repo.create_campaign(db_session, CampaignCreate(name="A"))
    await repo.create_campaign(db_session, CampaignCreate(name="B"))
    items = await repo.list_campaigns(db_session)
    assert len(items) >= 2


@pytest.mark.asyncio
async def test_delete_campaign(db_session, campaign):
    ok = await repo.delete_campaign(db_session, campaign.id)
    assert ok is True
    refetch = await repo.get_campaign(db_session, campaign.id)
    assert refetch is None


@pytest.mark.asyncio
async def test_create_campaign_job(db_session, campaign):
    data = CampaignJobCreate(
        campaign_id=campaign.id,
        platform="tiktok",
        device_id="device-abc",
    )
    job = await repo.create_campaign_job(db_session, data)
    assert job.id is not None
    assert job.status == "WAITING"
    assert job.priority == 2  # default NORMAL


@pytest.mark.asyncio
async def test_set_campaign_job_status(db_session, campaign):
    job_data = CampaignJobCreate(
        campaign_id=campaign.id,
        platform="tiktok",
        device_id="device-abc",
    )
    job = await repo.create_campaign_job(db_session, job_data)
    updated = await repo.set_campaign_job_status(db_session, job.id, "RUNNING")
    assert updated.status == "RUNNING"
    assert updated.started_at is not None


@pytest.mark.asyncio
async def test_record_and_list_history(db_session, campaign):
    await repo.record_history(
        db_session, "STARTED", campaign_id=campaign.id, detail="test"
    )
    history = await repo.list_history(db_session, campaign_id=campaign.id)
    assert len(history) == 1
    assert history[0].action == "STARTED"
