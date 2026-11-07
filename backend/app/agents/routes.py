"""
AI Agent Layer REST API.

Prefix: /api/v1/agents
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from .manager import agent_manager
from . import repository as repo
from .schemas import GoalSubmit, GoalUpdate, RecoverRequest, ForgetRequest
from . import memory as mem

router = APIRouter(prefix="/agents", tags=["agents"])


# ── Goals ─────────────────────────────────────────────────────────────────────

@router.get("/goals")
async def list_goals(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    goals = await repo.list_goals(db, status=status)
    return [g.to_dict() for g in goals]


@router.post("/goals", status_code=201)
async def submit_goal(
    data: GoalSubmit,
    db: AsyncSession = Depends(get_db),
) -> dict:
    goal = await agent_manager.submit_goal(db, data)
    return goal.to_dict()


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    g = await repo.get_goal(db, goal_id)
    if not g:
        raise HTTPException(404, "Goal not found")
    return g.to_dict()


@router.post("/goals/{goal_id}/pause")
async def pause_goal(goal_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    g = await agent_manager.pause_goal(db, goal_id)
    if not g:
        raise HTTPException(404, "Goal not found")
    return g.to_dict()


@router.post("/goals/{goal_id}/resume")
async def resume_goal(goal_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    g = await agent_manager.resume_goal(db, goal_id)
    if not g:
        raise HTTPException(404, "Goal not found")
    return g.to_dict()


@router.post("/goals/{goal_id}/cancel")
async def cancel_goal(goal_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    g = await agent_manager.cancel_goal(db, goal_id)
    if not g:
        raise HTTPException(404, "Goal not found")
    return g.to_dict()


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(
    goal_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    tasks = await repo.list_tasks(db, goal_id=goal_id, status=status, limit=limit)
    return [t.to_dict() for t in tasks]


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    t = await repo.get_task(db, task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    return t.to_dict()


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)) -> dict:
    return await agent_manager.get_status(db)


# ── Decisions ─────────────────────────────────────────────────────────────────

@router.get("/decisions")
async def list_decisions(
    goal_id: int | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    decisions = await repo.list_decisions(db, goal_id=goal_id, limit=limit)
    return [d.to_dict() for d in decisions]


# ── Memory ────────────────────────────────────────────────────────────────────

@router.get("/memory")
async def get_memory(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    entries = await mem.recall_all(db, category=category)
    return [e.to_dict() for e in entries]


@router.delete("/memory/{key}", status_code=204)
async def forget_memory(key: str, db: AsyncSession = Depends(get_db)) -> None:
    ok = await mem.forget(db, key)
    if not ok:
        raise HTTPException(404, "Memory key not found")


# ── Optimization ──────────────────────────────────────────────────────────────

@router.get("/suggestions")
async def get_suggestions(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await agent_manager.get_suggestions(db)


@router.post("/optimize")
async def run_optimization(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await agent_manager.trigger_optimization(db)


# ── Recovery ──────────────────────────────────────────────────────────────────

@router.post("/recover")
async def recover_job(
    req: RecoverRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await agent_manager.manual_recover(db, req.campaign_job_id, req.action)


# ── Timeline ─────────────────────────────────────────────────────────────────

@router.get("/timeline")
async def get_timeline(
    goal_id: int | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return decisions + task events as a chronological timeline."""
    decisions = await repo.list_decisions(db, goal_id=goal_id, limit=limit // 2)
    tasks = await repo.list_tasks(db, goal_id=goal_id, limit=limit // 2)

    events = []
    for d in decisions:
        events.append({
            "type": "decision",
            "ts": d.created_at.isoformat() if d.created_at else None,
            "agent": d.agent,
            "summary": f"{d.agent}: {d.decision} (confidence {d.confidence_pct:.0f}%)",
            "detail": d.to_dict(),
        })
    for t in tasks:
        events.append({
            "type": "task",
            "ts": t.updated_at.isoformat() if t.updated_at else None,
            "agent": t.agent,
            "summary": f"{t.agent} task {t.id}: {t.task_type} → {t.status}",
            "detail": t.to_dict(),
        })

    events.sort(key=lambda e: e["ts"] or "", reverse=True)
    return events[:limit]
