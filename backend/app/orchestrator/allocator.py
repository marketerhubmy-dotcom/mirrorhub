"""
Job-to-device allocator.

assign_device()       → pick one device for a single job
distribute_campaign() → spread all pending jobs in a campaign across the fleet
migrate_jobs()        → move WAITING/READY jobs from one device to another
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.campaign.models import CampaignJob
from .balancing import LoadBalancer
from .models import AVAILABLE_STATUSES
from .repository import (
    get_or_create_profile,
    list_available_profiles,
    record_assignment,
    record_migration,
)

logger = logging.getLogger(__name__)


async def assign_device(
    db: AsyncSession,
    job: CampaignJob,
    *,
    strategy: str = "least_busy",
    group_id: int | None = None,
    plugin_filter: str | None = None,
    active_jobs: dict[str, int] | None = None,
    manual_device_id: str | None = None,
    exclude_device_id: str | None = None,
) -> str | None:
    """
    Pick a device for `job` and stamp `job.device_id` + create an assignment record.

    Returns the chosen device_id, or None if no device is available.
    Does NOT commit — caller must commit after.
    """
    profiles = await list_available_profiles(db, plugin=plugin_filter, group_id=group_id)
    if exclude_device_id:  # failover: never hand the job back to the device it just left
        profiles = [p for p in profiles if p.device_id != exclude_device_id]
    if not profiles:
        logger.debug("assign_device: no available profiles for job %d", job.id)
        return None

    lb = LoadBalancer(strategy)
    chosen = lb.pick(
        profiles,
        active_jobs=active_jobs,
        manual_device_id=manual_device_id,
    )
    if not chosen:
        return None

    job.device_id = chosen.device_id
    reason = f"strategy={strategy}"
    if group_id:
        reason += f" group={group_id}"
    if plugin_filter:
        reason += f" plugin={plugin_filter}"

    await record_assignment(db, job.id, chosen.device_id, strategy=strategy, reason=reason)
    logger.info(
        "Assigned job %d to device %s via %s", job.id, chosen.device_id, strategy
    )
    return chosen.device_id


async def distribute_campaign(
    db: AsyncSession,
    campaign_id: int,
    *,
    strategy: str = "least_busy",
    group_id: int | None = None,
    plugin_filter: str | None = None,
    active_jobs: dict[str, int] | None = None,
) -> dict[str, int]:
    """
    Assign all unassigned (device_id IS NULL) WAITING jobs in a campaign.

    Returns {device_id: assigned_count}.
    """
    result = await db.execute(
        select(CampaignJob).where(
            CampaignJob.campaign_id == campaign_id,
            CampaignJob.status == "WAITING",
            CampaignJob.device_id.is_(None),
        )
    )
    jobs = list(result.scalars().all())
    if not jobs:
        return {}

    profiles = await list_available_profiles(db, plugin=plugin_filter, group_id=group_id)
    if not profiles:
        logger.warning(
            "distribute_campaign: no available profiles for campaign %d", campaign_id
        )
        return {}

    lb = LoadBalancer(strategy)
    allocations = lb.distribute(profiles, len(jobs), active_jobs=active_jobs)

    counts: dict[str, int] = {}
    job_iter = iter(jobs)
    for profile, n in allocations:
        for _ in range(n):
            job = next(job_iter, None)
            if not job:
                break
            job.device_id = profile.device_id
            await record_assignment(
                db, job.id, profile.device_id,
                strategy=strategy,
                reason=f"distribute_campaign cid={campaign_id}",
            )
            counts[profile.device_id] = counts.get(profile.device_id, 0) + 1

    await db.commit()
    logger.info(
        "distribute_campaign(%d): assigned %d jobs — %s",
        campaign_id, len(jobs), counts,
    )
    return counts


async def migrate_jobs(
    db: AsyncSession,
    from_device_id: str,
    to_device_id: str,
    job_statuses: list[str] | None = None,
) -> int:
    """
    Reassign all pending jobs from `from_device_id` to `to_device_id`.

    Only moves jobs whose status is in `job_statuses` (default: WAITING, READY).
    Returns the number of jobs moved.
    """
    if job_statuses is None:
        job_statuses = ["WAITING", "READY"]

    result = await db.execute(
        select(CampaignJob).where(
            CampaignJob.device_id == from_device_id,
            CampaignJob.status.in_(job_statuses),
        )
    )
    jobs = list(result.scalars().all())
    if not jobs:
        return 0

    for job in jobs:
        await record_migration(
            db, job.id, from_device_id, to_device_id, reason="migration"
        )
        job.device_id = to_device_id

    await db.commit()
    logger.info(
        "Migrated %d jobs from %s → %s", len(jobs), from_device_id, to_device_id
    )
    return len(jobs)
