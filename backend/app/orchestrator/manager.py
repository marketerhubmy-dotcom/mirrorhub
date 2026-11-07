"""
OrchestratorManager — singleton coordinator.

Provides the high-level API used by routes.py and the lifespan hook.
Delegates heavy lifting to allocator, balancing, monitor, repository.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from .allocator import assign_device, distribute_campaign, migrate_jobs
from .balancing import LoadBalancer, STRATEGY_NAMES
from .models import STATUS_MAINTENANCE, STATUS_IDLE, STATUS_OFFLINE
from .repository import (
    get_or_create_profile,
    list_profiles,
    list_available_profiles,
    update_profile_status,
    list_groups,
    list_group_members,
    list_assignments,
)

logger = logging.getLogger(__name__)


class OrchestratorManager:
    """
    Singleton that drives the orchestrator.

    The monitor loop is started/stopped by the FastAPI lifespan.
    Routes call methods here instead of touching the DB directly.
    """

    # ── Fleet status ─────────────────────────────────────────────────────────

    async def get_fleet_status(self, db: AsyncSession) -> dict[str, Any]:
        profiles = await list_profiles(db)
        return {
            "total": len(profiles),
            "online": sum(1 for p in profiles if p.status not in (STATUS_OFFLINE, "DISCONNECTED")),
            "idle": sum(1 for p in profiles if p.status == STATUS_IDLE),
            "busy": sum(1 for p in profiles if p.status == "BUSY"),
            "maintenance": sum(1 for p in profiles if p.status == STATUS_MAINTENANCE),
            "offline": sum(1 for p in profiles if p.status == STATUS_OFFLINE),
            "devices": [p.to_dict() for p in profiles],
        }

    # ── Device reservation / maintenance ─────────────────────────────────────

    async def set_device_maintenance(
        self, db: AsyncSession, device_id: str, *, reason: str = ""
    ) -> dict:
        profile = await update_profile_status(db, device_id, STATUS_MAINTENANCE)
        logger.info("Device %s → MAINTENANCE (%s)", device_id, reason)
        return profile.to_dict()

    async def release_device(self, db: AsyncSession, device_id: str) -> dict:
        profile = await update_profile_status(db, device_id, STATUS_IDLE)
        logger.info("Device %s released from MAINTENANCE/RESERVED", device_id)
        return profile.to_dict()

    async def reserve_device(
        self, db: AsyncSession, device_id: str, *, reason: str = ""
    ) -> dict:
        # MAINTENANCE doubles as "reserved" — monitor won't dispatch jobs to it
        profile = await update_profile_status(db, device_id, STATUS_MAINTENANCE)
        logger.info("Device %s reserved (%s)", device_id, reason)
        return profile.to_dict()

    # ── Distribution ──────────────────────────────────────────────────────────

    async def auto_distribute(
        self,
        db: AsyncSession,
        campaign_id: int,
        *,
        strategy: str = "least_busy",
        group_id: int | None = None,
        plugin_filter: str | None = None,
        active_jobs: dict[str, int] | None = None,
    ) -> dict[str, int]:
        return await distribute_campaign(
            db,
            campaign_id,
            strategy=strategy,
            group_id=group_id,
            plugin_filter=plugin_filter,
            active_jobs=active_jobs,
        )

    # ── Rebalance ────────────────────────────────────────────────────────────

    async def rebalance(
        self,
        db: AsyncSession,
        *,
        campaign_id: int | None = None,
        strategy: str = "least_busy",
    ) -> dict:
        """
        Re-assign WAITING jobs to level load across available devices.

        If campaign_id is given, only that campaign's jobs are rebalanced.
        """
        from sqlalchemy import select
        from app.campaign.models import CampaignJob

        q = select(CampaignJob).where(CampaignJob.status == "WAITING")
        if campaign_id:
            q = q.where(CampaignJob.campaign_id == campaign_id)

        result = await db.execute(q)
        jobs = list(result.scalars().all())
        if not jobs:
            return {"rebalanced": 0}

        # Null out device assignments so distribute_campaign can reassign
        for job in jobs:
            job.device_id = None
        await db.commit()

        if campaign_id:
            counts = await distribute_campaign(db, campaign_id, strategy=strategy)
        else:
            # Group by campaign and distribute each
            campaigns: dict[int, list[CampaignJob]] = {}
            for j in jobs:
                campaigns.setdefault(j.campaign_id, []).append(j)
            counts: dict[str, int] = {}
            for cid in campaigns:
                c = await distribute_campaign(db, cid, strategy=strategy)
                for dev, n in c.items():
                    counts[dev] = counts.get(dev, 0) + n

        return {"rebalanced": sum(counts.values()), "distribution": counts}

    # ── Migration ────────────────────────────────────────────────────────────

    async def migrate(
        self,
        db: AsyncSession,
        from_device_id: str,
        to_device_id: str,
        job_statuses: list[str] | None = None,
    ) -> dict:
        moved = await migrate_jobs(db, from_device_id, to_device_id, job_statuses)
        return {"moved": moved, "from": from_device_id, "to": to_device_id}

    # ── Stats ────────────────────────────────────────────────────────────────

    async def get_stats(self, db: AsyncSession, device_id: str | None = None) -> dict:
        if device_id:
            profile = await get_or_create_profile(db, device_id)
            assignments = await list_assignments(db, device_id=device_id, limit=50)
            return {
                "device": profile.to_dict(),
                "recent_assignments": [a.to_dict() for a in assignments],
            }
        profiles = await list_profiles(db)
        total_completed = sum(p.total_jobs_completed for p in profiles)
        total_failed = sum(p.total_jobs_failed for p in profiles)
        return {
            "fleet_total_completed": total_completed,
            "fleet_total_failed": total_failed,
            "fleet_success_rate": round(
                total_completed / max(total_completed + total_failed, 1) * 100, 1
            ),
            "devices": [
                {
                    "device_id": p.device_id,
                    "status": p.status,
                    "performance_score": p.performance_score,
                    "completed": p.total_jobs_completed,
                    "failed": p.total_jobs_failed,
                }
                for p in profiles
            ],
        }


# Singleton
orchestrator = OrchestratorManager()
