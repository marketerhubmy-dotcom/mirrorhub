"""
Orchestrator pre-dispatch scheduler.

When the campaign dispatcher is about to pick up a WAITING job that has
no device_id assigned, this scheduler fills it in before the dispatcher
proceeds. It runs as a lightweight async hook — no separate background loop.

Usage (from dispatcher or campaign routes):
    from app.orchestrator.scheduler import pre_assign_job
    await pre_assign_job(db, job)
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.campaign.models import CampaignJob
from .allocator import assign_device
from .models import AVAILABLE_STATUSES
from .repository import list_available_profiles

logger = logging.getLogger(__name__)


async def pre_assign_job(
    db: AsyncSession,
    job: CampaignJob,
    *,
    strategy: str = "least_busy",
    active_jobs: dict[str, int] | None = None,
) -> bool:
    """
    Assign a device to `job` if it doesn't have one.

    Returns True if a device was assigned (or was already assigned).
    Returns False if no device is available.

    This is called non-intrusively: the dispatcher runs unchanged.
    The job.device_id is set in-place; caller must commit.
    """
    if job.device_id:
        return True  # already assigned

    profiles = await list_available_profiles(db)
    if not profiles:
        logger.debug(
            "pre_assign_job: no available devices for job %d (campaign %d)",
            job.id, job.campaign_id,
        )
        return False

    device_id = await assign_device(
        db,
        job,
        strategy=strategy,
        active_jobs=active_jobs,
    )
    if device_id:
        await db.commit()
        logger.info(
            "pre_assign_job: job %d → %s", job.id, device_id
        )
    return bool(device_id)
