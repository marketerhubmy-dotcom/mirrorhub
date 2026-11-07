"""
Execution Agent.

Monitors active campaign jobs and orchestrates device assignment.
Does NOT modify the Execution Engine or Campaign Dispatcher.

Responsibilities:
  - Find WAITING CampaignJobs with no device assigned → assign via Orchestrator
  - Track RUNNING jobs, detect stalls, report to RecoveryAgent via manager event
  - Update goal task counts as jobs complete

Query efficiency:
  - Device active-job counts fetched in a single GROUP BY (not N per-device queries)
  - Goal progress counts fetched in a single GROUP BY per campaign (not 3 per goal)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaign.models import CampaignJob
from app.orchestrator.allocator import assign_device
from app.orchestrator.repository import list_available_profiles
from . import repository as repo
from .models import AgentGoal, MEM_DEVICE
from . import memory as mem

logger = logging.getLogger(__name__)

STALL_TIMEOUT_MINUTES = 10  # running job with no progress after this → flag


class ExecutionAgent:
    """Assigns devices to pending jobs and monitors running ones."""

    async def check(self, db: AsyncSession, active_goals: list[AgentGoal]) -> dict[str, int]:
        """
        Called each manager tick.

        Returns {assigned: N, stalled: N}.
        """
        assigned = 0
        stalled = 0

        campaign_ids = [g.campaign_id for g in active_goals if g.campaign_id]
        if not campaign_ids:
            return {"assigned": 0, "stalled": 0}

        # ── Assign devices to WAITING unassigned jobs ─────────────────────────
        result = await db.execute(
            select(CampaignJob).where(
                CampaignJob.campaign_id.in_(campaign_ids),
                CampaignJob.status == "WAITING",
                CampaignJob.device_id.is_(None),
            ).limit(20)
        )
        waiting = list(result.scalars().all())

        profiles = await list_available_profiles(db)
        if profiles and waiting:
            # Single GROUP BY query replaces N per-device queries
            device_ids = [p.device_id for p in profiles]
            jobs_result = await db.execute(
                select(
                    CampaignJob.device_id,
                    func.count(CampaignJob.id).label("running"),
                ).where(
                    CampaignJob.device_id.in_(device_ids),
                    CampaignJob.status == "RUNNING",
                ).group_by(CampaignJob.device_id)
            )
            active_jobs_map: dict[str, int] = {row.device_id: row.running for row in jobs_result}
            for p in profiles:
                active_jobs_map.setdefault(p.device_id, 0)

            for job in waiting:
                device_id = await assign_device(
                    db, job,
                    strategy="least_busy",
                    active_jobs=active_jobs_map,
                )
                if device_id:
                    assigned += 1
                    logger.debug("ExecutionAgent: job %d → device %s", job.id, device_id)

            if assigned:
                await db.commit()

        # ── Detect stalled RUNNING jobs ───────────────────────────────────────
        stall_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALL_TIMEOUT_MINUTES)
        stall_result = await db.execute(
            select(CampaignJob).where(
                CampaignJob.campaign_id.in_(campaign_ids),
                CampaignJob.status == "RUNNING",
                CampaignJob.started_at < stall_cutoff,
            )
        )
        stalled_jobs = list(stall_result.scalars().all())
        stalled = len(stalled_jobs)
        if stalled:
            logger.warning("ExecutionAgent: %d stalled jobs detected", stalled)

        # ── Update goal progress counts (single GROUP BY per campaign) ─────────
        counts_result = await db.execute(
            select(
                CampaignJob.campaign_id,
                func.sum(case((CampaignJob.status == "COMPLETED", 1), else_=0)).label("completed"),
                func.sum(case((CampaignJob.status == "FAILED", 1), else_=0)).label("failed"),
                func.count(CampaignJob.id).label("total"),
            ).where(
                CampaignJob.campaign_id.in_(campaign_ids),
            ).group_by(CampaignJob.campaign_id)
        )
        counts_by_campaign: dict[int, tuple[int, int, int]] = {
            row.campaign_id: (row.completed or 0, row.failed or 0, row.total or 0)
            for row in counts_result
        }

        for goal in active_goals:
            if not goal.campaign_id:
                continue
            completed, failed, total = counts_by_campaign.get(goal.campaign_id, (0, 0, 0))

            if completed != goal.tasks_completed or failed != goal.tasks_failed:
                goal.tasks_completed = completed
                goal.tasks_failed = failed
                goal.updated_at = datetime.now(timezone.utc)
                if total > 0 and (completed + failed) >= total:
                    goal.status = "COMPLETED" if completed > 0 else "FAILED"
                    logger.info(
                        "Goal %d completed: %d/%d done, %d failed",
                        goal.id, completed, total, failed,
                    )
        await db.commit()

        return {"assigned": assigned, "stalled": stalled}


execution_agent = ExecutionAgent()
