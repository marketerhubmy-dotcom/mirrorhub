"""
Optimization Agent.

Runs periodically (every N manager ticks) to:
  1. Analyze execution history (CampaignHistory + DeviceProfile + ExecutionJob)
  2. Compute device and plugin performance
  3. Store optimization recommendations in AgentMemory
  4. Return a list of suggestion dicts

Suggestions are always advisory — the user and/or other agents act on them.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaign.models import CampaignJob, CampaignHistory
from app.orchestrator.models import DeviceProfile
from . import memory as mem
from .knowledge import OPTIMIZATION_AREAS

logger = logging.getLogger(__name__)


class OptimizationAgent:
    """Analyzes history and produces advisory recommendations."""

    async def analyze(self, db: AsyncSession) -> list[dict]:
        """
        Full analysis pass. Returns a list of suggestions.
        Stores results in AgentMemory.
        """
        suggestions: list[dict] = []

        try:
            s = await self._device_performance(db)
            suggestions.extend(s)
        except Exception:
            logger.exception("OptimizationAgent: device_performance failed")

        try:
            s = await self._plugin_reliability(db)
            suggestions.extend(s)
        except Exception:
            logger.exception("OptimizationAgent: plugin_reliability failed")

        try:
            s = await self._retry_analysis(db)
            suggestions.extend(s)
        except Exception:
            logger.exception("OptimizationAgent: retry_analysis failed")

        # Store all suggestions in memory
        for i, s in enumerate(suggestions):
            await mem.remember_optimization(
                db,
                key=f"{s['area']}:{i}",
                recommendation=s["recommendation"],
                data=s,
            )

        logger.info("OptimizationAgent: %d suggestions generated", len(suggestions))
        return suggestions

    async def _device_performance(self, db: AsyncSession) -> list[dict]:
        """Find underperforming and top-performing devices."""
        result = await db.execute(select(DeviceProfile))
        profiles = list(result.scalars().all())
        suggestions = []

        for p in profiles:
            total = p.total_jobs_completed + p.total_jobs_failed
            if total < 5:
                continue  # not enough data

            success_rate = p.total_jobs_completed / total * 100

            # Remember device performance in memory
            await mem.remember_device_performance(
                db,
                device_id=p.device_id,
                jobs_completed=p.total_jobs_completed,
                jobs_failed=p.total_jobs_failed,
                avg_latency_ms=p.latency_ms,
                performance_score=p.performance_score,
            )

            if success_rate < 60:
                suggestions.append({
                    "area": "device_selection",
                    "severity": "warning",
                    "device_id": p.device_id,
                    "recommendation": (
                        f"Device {p.device_id[:8]} has {success_rate:.0f}% success rate "
                        f"({p.total_jobs_failed} failures). Consider maintenance or exclusion."
                    ),
                    "data": {
                        "success_rate": round(success_rate, 1),
                        "jobs_completed": p.total_jobs_completed,
                        "jobs_failed": p.total_jobs_failed,
                    },
                })
            elif p.performance_score >= 8.0 and success_rate >= 90:
                suggestions.append({
                    "area": "device_selection",
                    "severity": "info",
                    "device_id": p.device_id,
                    "recommendation": (
                        f"Device {p.device_id[:8]} is a top performer "
                        f"(score {p.performance_score:.1f}, {success_rate:.0f}% success). "
                        "Prioritize for critical campaigns."
                    ),
                    "data": {
                        "performance_score": p.performance_score,
                        "success_rate": round(success_rate, 1),
                    },
                })

        return suggestions

    async def _plugin_reliability(self, db: AsyncSession) -> list[dict]:
        """Analyze failure rates per plugin/platform."""
        since = datetime.now(timezone.utc) - timedelta(days=7)
        result = await db.execute(
            select(
                CampaignJob.platform,
                func.count(CampaignJob.id).label("total"),
                func.sum(
                    case((CampaignJob.status == "FAILED", 1), else_=0)
                ).label("failed"),
            ).where(
                CampaignJob.created_at >= since
            ).group_by(CampaignJob.platform)
        )
        rows = result.all()
        suggestions = []

        for row in rows:
            platform, total, failed = row.platform, row.total, row.failed or 0
            if total < 5:
                continue
            failure_rate = failed / total * 100
            success_rate = 100 - failure_rate

            await mem.remember_plugin_reliability(
                db,
                plugin=platform,
                success_count=total - failed,
                failure_count=failed,
                common_errors=[],
            )

            if failure_rate > 30:
                suggestions.append({
                    "area": "plugin_choice",
                    "severity": "warning",
                    "platform": platform,
                    "recommendation": (
                        f"Plugin '{platform}' has {failure_rate:.0f}% failure rate "
                        f"in the last 7 days ({failed}/{total} failed). "
                        "Review plugin configuration or switch workflows."
                    ),
                    "data": {
                        "platform": platform,
                        "failure_rate": round(failure_rate, 1),
                        "total": total,
                        "failed": failed,
                    },
                })

        return suggestions

    async def _retry_analysis(self, db: AsyncSession) -> list[dict]:
        """Flag jobs with excessive retries."""
        result = await db.execute(
            select(CampaignJob).where(
                CampaignJob.retry_count >= 2,
                CampaignJob.status.in_(["FAILED", "WAITING"]),
            ).limit(20)
        )
        high_retry = list(result.scalars().all())
        suggestions = []

        if len(high_retry) >= 5:
            suggestions.append({
                "area": "retry_strategy",
                "severity": "warning",
                "recommendation": (
                    f"{len(high_retry)} jobs have retried 2+ times. "
                    "Consider increasing retry delays or switching devices. "
                    "Frequent retries indicate a systemic issue."
                ),
                "data": {
                    "high_retry_count": len(high_retry),
                    "job_ids": [j.id for j in high_retry[:5]],
                },
            })

        return suggestions


optimization_agent = OptimizationAgent()
