"""
AgentManager — singleton orchestrator for the AI Agent Layer.

The manager runs a single background asyncio task that:
  1. Picks up PLANNING goals → runs PlannerAgent
  2. Runs QUEUED content tasks → ContentAgent (max N per tick)
  3. Runs ExecutionAgent.check() each tick
  4. Runs RecoveryAgent.check() each tick
  5. Every OPTIMIZATION_INTERVAL ticks → runs OptimizationAgent
  6. Broadcasts WebSocket events after significant state changes

Agents NEVER call each other.
All cross-agent communication passes through this class.

LOOP_INTERVAL: seconds between manager ticks (default 15).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from . import repository as repo
from .models import (
    AgentGoal, AgentTask,
    GOAL_PLANNING, GOAL_RUNNING, GOAL_FAILED,
    TASK_GENERATE_CONTENT, TASK_QUEUED,
)
from .planner import planner_agent
from .content_agent import content_agent
from .execution_agent import execution_agent
from .recovery_agent import recovery_agent
from .optimization_agent import optimization_agent
from .schemas import GoalSubmit

logger = logging.getLogger(__name__)

LOOP_INTERVAL: float = 15.0          # seconds between ticks
CONTENT_TASKS_PER_TICK: int = 3      # max content generation tasks per tick
OPTIMIZATION_INTERVAL: int = 20     # run optimizer every N ticks

_stop_event = asyncio.Event()
_tick_count: int = 0


def stop_agents() -> None:
    _stop_event.set()


# ── Public API (called by routes + lifespan) ──────────────────────────────────

class AgentManager:

    async def submit_goal(self, db: AsyncSession, data: GoalSubmit) -> AgentGoal:
        """Create and queue a new goal. Planner will handle it on the next tick."""
        goal = await repo.create_goal(
            db,
            goal_text=data.goal_text,
            platform=data.platform,
            product=data.product,
            target_count=data.target_count,
            priority=data.priority,
        )
        logger.info("AgentManager: goal %d submitted — '%s'", goal.id, data.goal_text[:60])
        await _broadcast("goal_submitted", {"goal_id": goal.id, "goal_text": data.goal_text})
        return goal

    async def pause_goal(self, db: AsyncSession, goal_id: int) -> AgentGoal | None:
        goal = await repo.get_goal(db, goal_id)
        if goal and goal.status == GOAL_RUNNING:
            await repo.update_goal_status(db, goal, "PAUSED")
            await _broadcast("goal_paused", {"goal_id": goal_id})
        return goal

    async def resume_goal(self, db: AsyncSession, goal_id: int) -> AgentGoal | None:
        goal = await repo.get_goal(db, goal_id)
        if goal and goal.status == "PAUSED":
            await repo.update_goal_status(db, goal, GOAL_RUNNING)
            await _broadcast("goal_resumed", {"goal_id": goal_id})
        return goal

    async def cancel_goal(self, db: AsyncSession, goal_id: int) -> AgentGoal | None:
        goal = await repo.get_goal(db, goal_id)
        if goal and goal.status not in ("COMPLETED", "CANCELLED"):
            await repo.update_goal_status(db, goal, "CANCELLED")
            await _broadcast("goal_cancelled", {"goal_id": goal_id})
        return goal

    async def get_status(self, db: AsyncSession) -> dict[str, Any]:
        active = await repo.list_active_goals(db)
        pending_content = await repo.list_pending_tasks(db, task_type=TASK_GENERATE_CONTENT)
        decisions = await repo.list_decisions(db, limit=5)
        return {
            "active_goals": len(active),
            "goals": [g.to_dict() for g in active],
            "pending_content_tasks": len(pending_content),
            "recent_decisions": [d.to_dict() for d in decisions],
            "loop_interval_s": LOOP_INTERVAL,
            "tick_count": _tick_count,
        }

    async def get_suggestions(self, db: AsyncSession) -> list[dict]:
        from . import memory as mem
        return await mem.get_optimization_history(db)

    async def trigger_optimization(self, db: AsyncSession) -> list[dict]:
        suggestions = await optimization_agent.analyze(db)
        await _broadcast("optimization_complete", {"suggestion_count": len(suggestions)})
        return suggestions

    async def manual_recover(
        self, db: AsyncSession, campaign_job_id: int, action: str
    ) -> dict:
        from app.campaign.models import CampaignJob
        from sqlalchemy import select

        result = await db.execute(
            select(CampaignJob).where(CampaignJob.id == campaign_job_id)
        )
        job = result.scalar_one_or_none()
        if not job:
            return {"error": "Job not found"}
        active_goals = await repo.list_active_goals(db)
        return await recovery_agent.recover_job(db, job, action, active_goals)


# ── Background loop ───────────────────────────────────────────────────────────

async def run_loop() -> None:
    global _tick_count
    logger.info("AgentManager loop started (interval=%.0fs)", LOOP_INTERVAL)
    _stop_event.clear()

    while not _stop_event.is_set():
        try:
            await _tick()
            _tick_count += 1
        except Exception:
            logger.exception("AgentManager tick error")

        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=LOOP_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def _tick() -> None:
    """
    One manager loop iteration.

    Each agent phase opens and closes its own short-lived DB session so that
    SQLite write locks are released between phases. Long GPT calls (planner,
    content, recovery) no longer hold a write lock for the duration of the tick.
    """
    # ── Phase 1: Plan any new goals ───────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        active_goals = await repo.list_active_goals(db)
        planning = [g for g in active_goals if g.status == GOAL_PLANNING]
        for goal in planning:
            try:
                await _broadcast("agent_started", {"agent": "planner", "goal_id": goal.id})
                plan = await planner_agent.plan(db, goal)
                await _broadcast("task_assigned", {
                    "agent": "planner",
                    "goal_id": goal.id,
                    "plan_summary": f"{plan.get('count')} jobs for {plan.get('platform')}",
                })
            except Exception as exc:
                logger.exception("PlannerAgent failed for goal %d: %s", goal.id, exc)
                await repo.update_goal_status(db, goal, GOAL_FAILED, error=str(exc))
                await _broadcast("goal_failed", {"goal_id": goal.id, "error": str(exc)})

    # ── Phase 2: Run content generation tasks ─────────────────────────────────
    async with AsyncSessionLocal() as db:
        active_goals = await repo.list_active_goals(db)
        running = [g for g in active_goals if g.status == GOAL_RUNNING]
        running_goal_ids = {g.id for g in running}
        pending_content = await repo.list_pending_tasks(db, task_type=TASK_GENERATE_CONTENT)
        pending_content = [t for t in pending_content if t.goal_id in running_goal_ids]
        for task in pending_content[:CONTENT_TASKS_PER_TICK]:
            await _broadcast("agent_started", {"agent": "content", "task_id": task.id})
            await content_agent.run_task(db, task)
            await _broadcast("task_assigned", {
                "agent": "content",
                "task_id": task.id,
                "status": task.status,
            })

    # ── Phase 3: Execution monitoring ─────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        active_goals = await repo.list_active_goals(db)
        running = [g for g in active_goals if g.status == GOAL_RUNNING]
        if running:
            exec_result = await execution_agent.check(db, running)
            if exec_result.get("assigned"):
                await _broadcast("task_assigned", {
                    "agent": "execution",
                    "assigned": exec_result["assigned"],
                })
            if exec_result.get("stalled"):
                await _broadcast("decision_made", {
                    "agent": "execution",
                    "decision": "stall_detected",
                    "count": exec_result["stalled"],
                })

    # ── Phase 4: Recovery ─────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        active_goals = await repo.list_active_goals(db)
        running = [g for g in active_goals if g.status == GOAL_RUNNING]
        if running:
            actions = await recovery_agent.check(db, running)
            for action in actions:
                await _broadcast("recovery_started", action)

    # ── Phase 5: Periodic optimization ────────────────────────────────────────
    if _tick_count % OPTIMIZATION_INTERVAL == 0 and _tick_count > 0:
        async with AsyncSessionLocal() as db:
            suggestions = await optimization_agent.analyze(db)
            if suggestions:
                await _broadcast("optimization_suggested", {
                    "count": len(suggestions),
                    "areas": list({s["area"] for s in suggestions}),
                })

    # ── Phase 6: Goal completion check ────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        active_goals = await repo.list_active_goals(db)
        running = [g for g in active_goals if g.status == GOAL_RUNNING]
        for goal in running:
            if goal.tasks_total > 0 and (goal.tasks_completed + goal.tasks_failed) >= goal.tasks_total:
                await repo.update_goal_status(db, goal, "COMPLETED")
                await _broadcast("goal_completed", {
                    "goal_id": goal.id,
                    "completed": goal.tasks_completed,
                    "failed": goal.tasks_failed,
                })


async def _broadcast(event: str, data: dict) -> None:
    try:
        from app.websocket.manager import manager
        payload = json.dumps({"event": event, "data": data, "ts": datetime.now(timezone.utc).isoformat()})
        await manager.broadcast_agent(payload)
    except Exception:
        pass  # best-effort


# Singleton
agent_manager = AgentManager()
