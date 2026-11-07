"""CRUD helpers for the Agent Layer models."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AgentGoal, AgentTask, AgentDecision, AgentMemoryEntry,
    GOAL_PLANNING, TASK_CREATED,
)


# ── AgentGoal ─────────────────────────────────────────────────────────────────

async def create_goal(
    db: AsyncSession,
    goal_text: str,
    platform: str,
    product: str,
    target_count: int,
    priority: int,
) -> AgentGoal:
    g = AgentGoal(
        goal_text=goal_text,
        platform=platform,
        product=product,
        target_count=target_count,
        priority=priority,
        status=GOAL_PLANNING,
    )
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return g


async def get_goal(db: AsyncSession, goal_id: int) -> AgentGoal | None:
    return await db.get(AgentGoal, goal_id)


async def list_goals(db: AsyncSession, status: str | None = None) -> list[AgentGoal]:
    q = select(AgentGoal).order_by(AgentGoal.created_at.desc())
    if status:
        q = q.where(AgentGoal.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


async def list_active_goals(db: AsyncSession) -> list[AgentGoal]:
    result = await db.execute(
        select(AgentGoal).where(
            AgentGoal.status.in_(["PLANNING", "RUNNING"])
        ).order_by(AgentGoal.priority)
    )
    return list(result.scalars().all())


async def update_goal_status(db: AsyncSession, goal: AgentGoal, status: str, error: str | None = None) -> AgentGoal:
    goal.status = status
    goal.updated_at = datetime.now(timezone.utc)
    if error:
        goal.error = error
    await db.commit()
    return goal


async def update_goal_plan(db: AsyncSession, goal: AgentGoal, plan: dict) -> AgentGoal:
    goal.plan_json = json.dumps(plan)
    goal.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return goal


async def update_goal_result(db: AsyncSession, goal: AgentGoal, result: dict) -> AgentGoal:
    goal.result_json = json.dumps(result)
    goal.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return goal


async def increment_goal_task_counts(db: AsyncSession, goal: AgentGoal, completed: int = 0, failed: int = 0) -> None:
    goal.tasks_completed += completed
    goal.tasks_failed += failed
    goal.updated_at = datetime.now(timezone.utc)
    await db.commit()


# ── AgentTask ─────────────────────────────────────────────────────────────────

async def create_task(
    db: AsyncSession,
    goal_id: int,
    task_type: str,
    agent: str,
    input_data: dict,
) -> AgentTask:
    t = AgentTask(
        goal_id=goal_id,
        task_type=task_type,
        agent=agent,
        status=TASK_CREATED,
        input_json=json.dumps(input_data),
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def get_task(db: AsyncSession, task_id: int) -> AgentTask | None:
    return await db.get(AgentTask, task_id)


async def list_tasks(
    db: AsyncSession,
    goal_id: int | None = None,
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 100,
) -> list[AgentTask]:
    q = select(AgentTask).order_by(AgentTask.created_at.desc()).limit(limit)
    if goal_id:
        q = q.where(AgentTask.goal_id == goal_id)
    if status:
        q = q.where(AgentTask.status == status)
    if task_type:
        q = q.where(AgentTask.task_type == task_type)
    result = await db.execute(q)
    return list(result.scalars().all())


async def list_pending_tasks(db: AsyncSession, task_type: str | None = None) -> list[AgentTask]:
    q = select(AgentTask).where(AgentTask.status.in_(["CREATED", "QUEUED"])).order_by(AgentTask.created_at)
    if task_type:
        q = q.where(AgentTask.task_type == task_type)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_task(
    db: AsyncSession,
    task: AgentTask,
    status: str,
    output: dict | None = None,
    error: str | None = None,
) -> AgentTask:
    task.status = status
    task.updated_at = datetime.now(timezone.utc)
    if output is not None:
        task.output_json = json.dumps(output)
    if error is not None:
        task.error = error
    await db.commit()
    return task


# ── AgentDecision ─────────────────────────────────────────────────────────────

async def record_decision(
    db: AsyncSession,
    agent: str,
    decision: str,
    reason: str,
    confidence: float,
    alternative: str = "",
    expected_result: str = "",
    goal_id: int | None = None,
    task_id: int | None = None,
    was_failsafe: bool = False,
) -> AgentDecision:
    d = AgentDecision(
        goal_id=goal_id,
        task_id=task_id,
        agent=agent,
        decision=decision,
        reason=reason,
        confidence=confidence,
        alternative=alternative,
        expected_result=expected_result,
        was_failsafe=was_failsafe,
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


async def list_decisions(
    db: AsyncSession,
    goal_id: int | None = None,
    limit: int = 50,
) -> list[AgentDecision]:
    q = select(AgentDecision).order_by(AgentDecision.created_at.desc()).limit(limit)
    if goal_id:
        q = q.where(AgentDecision.goal_id == goal_id)
    result = await db.execute(q)
    return list(result.scalars().all())


# ── AgentMemoryEntry ──────────────────────────────────────────────────────────

async def remember(
    db: AsyncSession,
    key: str,
    category: str,
    value: dict,
    summary: str = "",
) -> AgentMemoryEntry:
    """Upsert a memory entry."""
    result = await db.execute(select(AgentMemoryEntry).where(AgentMemoryEntry.key == key))
    entry = result.scalar_one_or_none()
    if entry:
        entry.value_json = json.dumps(value)
        entry.summary = summary or entry.summary
        entry.updated_at = datetime.now(timezone.utc)
        entry.access_count += 1
        entry.last_used_at = datetime.now(timezone.utc)
    else:
        entry = AgentMemoryEntry(
            key=key,
            category=category,
            summary=summary,
            value_json=json.dumps(value),
        )
        db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def recall(
    db: AsyncSession,
    key: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[AgentMemoryEntry]:
    q = select(AgentMemoryEntry).order_by(
        AgentMemoryEntry.relevance_score.desc(),
        AgentMemoryEntry.last_used_at.desc(),
    ).limit(limit)
    if key:
        q = q.where(AgentMemoryEntry.key == key)
    if category:
        q = q.where(AgentMemoryEntry.category == category)
    result = await db.execute(q)
    entries = list(result.scalars().all())
    # Update last_used_at for recalled entries
    for e in entries:
        e.access_count += 1
        e.last_used_at = datetime.now(timezone.utc)
    if entries:
        await db.commit()
    return entries


async def forget(db: AsyncSession, key: str) -> bool:
    result = await db.execute(select(AgentMemoryEntry).where(AgentMemoryEntry.key == key))
    entry = result.scalar_one_or_none()
    if not entry:
        return False
    await db.delete(entry)
    await db.commit()
    return True
