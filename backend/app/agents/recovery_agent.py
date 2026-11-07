"""
Recovery Agent.

Monitors FAILED CampaignJobs within active goals and decides what to do.

Decision tree (via AI reasoning):
  retry      → increment retry_count, reset to WAITING
  reassign   → find a different device, reset to WAITING
  pause      → pause the campaign
  abort      → leave as FAILED, log it

FAILSAFE: if AI confidence < threshold, returns "needs_review" decision request
without touching the job — the manager broadcasts a request_review event.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaign.models import CampaignJob
from app.orchestrator.repository import list_available_profiles
from . import repository as repo
from .models import AgentGoal, MEM_PLUGIN
from .reasoning import reason, FAILSAFE_THRESHOLD
from . import memory as mem

logger = logging.getLogger(__name__)


class RecoveryAgent:
    """Handles failed jobs in active goals."""

    async def check(self, db: AsyncSession, active_goals: list[AgentGoal]) -> list[dict]:
        """
        Check all active goals for failed jobs.

        Returns list of recovery action dicts.
        """
        actions = []
        campaign_ids = [g.campaign_id for g in active_goals if g.campaign_id]
        if not campaign_ids:
            return actions

        result = await db.execute(
            select(CampaignJob).where(
                CampaignJob.campaign_id.in_(campaign_ids),
                CampaignJob.status == "FAILED",
                CampaignJob.retry_count < CampaignJob.retry_max,
            ).limit(10)
        )
        failed_jobs = list(result.scalars().all())

        for job in failed_jobs:
            action = await self._decide_recovery(db, job, active_goals)
            if action:
                actions.append(action)

        return actions

    async def recover_job(
        self,
        db: AsyncSession,
        job: CampaignJob,
        action: str,
        active_goals: list[AgentGoal],
    ) -> dict:
        """
        Execute a specific recovery action on a job.

        Used by routes for manual recovery requests.
        """
        return await self._execute_action(db, job, action, active_goals)

    async def _decide_recovery(
        self, db: AsyncSession, job: CampaignJob, active_goals: list[AgentGoal]
    ) -> dict | None:
        """Use AI reasoning to decide what to do with a failed job."""
        # Build context
        profiles = await list_available_profiles(db)
        other_devices = [p.device_id for p in profiles if p.device_id != job.device_id]

        plugin_mem = await mem.get_plugin_reliability(db, job.platform)
        device_mem = await mem.get_device_performance_summary(db, job.device_id or "unknown")

        context = (
            f"Failed CampaignJob #{job.id}\n"
            f"Platform: {job.platform}\n"
            f"Error: {job.error or 'unknown'}\n"
            f"Retry count: {job.retry_count}/{job.retry_max}\n"
            f"Device: {job.device_id or 'none'}\n"
            f"Other available devices: {len(other_devices)}\n"
            f"Plugin reliability: {plugin_mem.get('reliability_rate', '?')}%\n"
            f"Device success rate: {device_mem.get('success_rate', '?')}%\n"
        )

        options = ["retry", "reassign", "pause", "abort"]
        if not other_devices:
            options = ["retry", "pause", "abort"]
        if job.retry_count >= job.retry_max:
            options = ["reassign", "abort"] if other_devices else ["abort"]

        r = await reason(context, options, agent_name="recovery")

        # Record the decision
        goal_id = next((g.id for g in active_goals if g.campaign_id == job.campaign_id), None)
        await repo.record_decision(
            db,
            agent="recovery",
            decision=r.decision,
            reason=r.reason,
            confidence=r.confidence,
            alternative=r.alternative,
            expected_result=r.expected_result,
            goal_id=goal_id,
            was_failsafe=r.was_failsafe,
        )

        if r.was_failsafe:
            return {
                "action": "needs_review",
                "job_id": job.id,
                "reason": r.reason,
                "confidence": r.confidence,
            }

        return await self._execute_action(db, job, r.decision, active_goals)

    async def _execute_action(
        self, db: AsyncSession, job: CampaignJob, action: str, active_goals: list[AgentGoal]
    ) -> dict:
        if action == "retry":
            job.retry_count += 1
            job.status = "WAITING"
            job.error = None
            job.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("RecoveryAgent: job %d → RETRY (%d/%d)", job.id, job.retry_count, job.retry_max)
            return {"action": "retry", "job_id": job.id, "retry_count": job.retry_count}

        elif action == "reassign":
            profiles = await list_available_profiles(db)
            candidates = [p for p in profiles if p.device_id != job.device_id]
            if candidates:
                best = max(candidates, key=lambda p: p.performance_score)
                old_device = job.device_id
                job.device_id = best.device_id
                job.status = "WAITING"
                job.retry_count += 1
                job.error = None
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info("RecoveryAgent: job %d reassigned %s → %s", job.id, old_device, best.device_id)
                return {"action": "reassign", "job_id": job.id, "from": old_device, "to": best.device_id}
            else:
                # Fall back to retry on same device
                job.retry_count += 1
                job.status = "WAITING"
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                return {"action": "retry_fallback", "job_id": job.id}

        elif action == "pause":
            goal = next((g for g in active_goals if g.campaign_id == job.campaign_id), None)
            if goal:
                goal.status = "PAUSED"
                goal.updated_at = datetime.now(timezone.utc)
                await db.commit()
                logger.info("RecoveryAgent: goal %d paused due to repeated failures", goal.id)
            return {"action": "pause", "job_id": job.id, "campaign_id": job.campaign_id}

        else:  # abort
            logger.info("RecoveryAgent: job %d aborted", job.id)
            return {"action": "abort", "job_id": job.id}


recovery_agent = RecoveryAgent()
