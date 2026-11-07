"""Database CRUD helpers for the Campaign module."""
import json
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Campaign, CampaignJob, ExecutionQueue, CampaignHistory
from .schemas import CampaignCreate, CampaignUpdate, CampaignJobCreate, CampaignJobUpdate


# ── Campaign ──────────────────────────────────────────────────────────────────

async def create_campaign(db: AsyncSession, data: CampaignCreate) -> Campaign:
    c = Campaign(
        name=data.name,
        description=data.description,
        platform_default=data.platform_default,
        device_id_default=data.device_id_default,
        timezone=data.timezone,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def get_campaign(db: AsyncSession, campaign_id: int) -> Campaign | None:
    return await db.get(Campaign, campaign_id)


async def list_campaigns(db: AsyncSession) -> list[Campaign]:
    result = await db.execute(select(Campaign).order_by(Campaign.updated_at.desc()))
    return list(result.scalars().all())


async def update_campaign(db: AsyncSession, campaign_id: int, data: CampaignUpdate) -> Campaign | None:
    c = await db.get(Campaign, campaign_id)
    if not c:
        return None
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(c)
    return c


async def delete_campaign(db: AsyncSession, campaign_id: int) -> bool:
    c = await db.get(Campaign, campaign_id)
    if not c:
        return False
    await db.delete(c)
    await db.commit()
    return True


async def refresh_campaign_counts(db: AsyncSession, campaign_id: int) -> None:
    """Recompute total/completed/failed counts from CampaignJob rows."""
    c = await db.get(Campaign, campaign_id)
    if not c:
        return
    rows = await db.execute(
        select(CampaignJob.status, func.count(CampaignJob.id))
        .where(CampaignJob.campaign_id == campaign_id)
        .group_by(CampaignJob.status)
    )
    counts: dict[str, int] = {row[0]: row[1] for row in rows}
    c.total_jobs = sum(counts.values())
    c.completed_jobs = counts.get("COMPLETED", 0)
    c.failed_jobs = counts.get("FAILED", 0)
    await db.commit()


# ── CampaignJob ───────────────────────────────────────────────────────────────

async def create_campaign_job(db: AsyncSession, data: CampaignJobCreate) -> CampaignJob:
    cj = CampaignJob(
        campaign_id=data.campaign_id,
        content_job_id=data.content_job_id,
        platform=data.platform,
        device_id=data.device_id,
        priority=data.priority,
        scheduled_time=data.scheduled_time,
        schedule_expr=json.dumps(data.schedule_expr) if data.schedule_expr else None,
        depends_on_job_id=data.depends_on_job_id,
        retry_max=data.retry_max,
        job_config_json=json.dumps(data.job_config),
    )
    db.add(cj)
    await db.commit()
    await db.refresh(cj)
    # Update campaign job count
    c = await db.get(Campaign, data.campaign_id)
    if c:
        c.total_jobs = (c.total_jobs or 0) + 1
        await db.commit()
    return cj


async def get_campaign_job(db: AsyncSession, job_id: int) -> CampaignJob | None:
    return await db.get(CampaignJob, job_id)


async def list_campaign_jobs(db: AsyncSession, campaign_id: int) -> list[CampaignJob]:
    result = await db.execute(
        select(CampaignJob)
        .where(CampaignJob.campaign_id == campaign_id)
        .order_by(CampaignJob.priority, CampaignJob.scheduled_time)
    )
    return list(result.scalars().all())


async def update_campaign_job(db: AsyncSession, job_id: int, data: CampaignJobUpdate) -> CampaignJob | None:
    cj = await db.get(CampaignJob, job_id)
    if not cj:
        return None
    for k, v in data.model_dump(exclude_none=True).items():
        if k == "job_config":
            cj.job_config_json = json.dumps(v)
        elif k == "schedule_expr":
            cj.schedule_expr = json.dumps(v) if v else None
        elif hasattr(cj, k):
            setattr(cj, k, v)
    cj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(cj)
    return cj


async def set_campaign_job_status(
    db: AsyncSession, job_id: int, status: str,
    error: str | None = None,
    execution_job_id: int | None = None,
) -> CampaignJob | None:
    cj = await db.get(CampaignJob, job_id)
    if not cj:
        return None
    cj.status = status
    if error is not None:
        cj.error = error
    if execution_job_id is not None:
        cj.execution_job_id = execution_job_id
    if status == "RUNNING" and not cj.started_at:
        cj.started_at = datetime.now(timezone.utc)
    if status in ("COMPLETED", "FAILED", "CANCELLED"):
        cj.finished_at = datetime.now(timezone.utc)
    cj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(cj)
    return cj


# ── ExecutionQueue ────────────────────────────────────────────────────────────

async def enqueue(db: AsyncSession, campaign_job_id: int, queue_order: int = 0) -> ExecutionQueue:
    entry = ExecutionQueue(
        campaign_job_id=campaign_job_id,
        queue_order=queue_order,
        status="WAITING",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def get_queue_entry(db: AsyncSession, entry_id: int) -> ExecutionQueue | None:
    return await db.get(ExecutionQueue, entry_id)


async def get_queue_entry_by_job(db: AsyncSession, campaign_job_id: int) -> ExecutionQueue | None:
    result = await db.execute(
        select(ExecutionQueue)
        .where(ExecutionQueue.campaign_job_id == campaign_job_id)
        .order_by(ExecutionQueue.id.desc())
    )
    return result.scalars().first()


async def list_queue(db: AsyncSession, limit: int = 200) -> list[ExecutionQueue]:
    result = await db.execute(
        select(ExecutionQueue)
        .order_by(ExecutionQueue.queue_order, ExecutionQueue.id)
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_active_queue(db: AsyncSession) -> list[ExecutionQueue]:
    """WAITING + READY + RUNNING + RETRY entries."""
    result = await db.execute(
        select(ExecutionQueue)
        .where(ExecutionQueue.status.in_(["WAITING", "READY", "RUNNING", "RETRY", "PAUSED"]))
        .order_by(ExecutionQueue.queue_order, ExecutionQueue.id)
    )
    return list(result.scalars().all())


async def update_queue_entry_status(
    db: AsyncSession, entry_id: int, status: str,
) -> ExecutionQueue | None:
    entry = await db.get(ExecutionQueue, entry_id)
    if not entry:
        return None
    entry.status = status
    if status == "RUNNING":
        entry.started_at = datetime.now(timezone.utc)
    if status in ("COMPLETED", "FAILED", "CANCELLED"):
        entry.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    return entry


async def reorder_queue_entry(db: AsyncSession, campaign_job_id: int, new_order: int) -> None:
    entry = await get_queue_entry_by_job(db, campaign_job_id)
    if entry:
        entry.queue_order = new_order
        await db.commit()


# ── CampaignHistory ───────────────────────────────────────────────────────────

async def record_history(
    db: AsyncSession,
    action: str,
    campaign_id: int | None = None,
    campaign_job_id: int | None = None,
    result: str = "OK",
    detail: str = "",
    duration_s: float = 0.0,
) -> CampaignHistory:
    h = CampaignHistory(
        campaign_id=campaign_id,
        campaign_job_id=campaign_job_id,
        action=action,
        result=result,
        detail=detail,
        duration_s=duration_s,
    )
    db.add(h)
    await db.commit()
    return h


async def list_history(
    db: AsyncSession,
    campaign_id: int | None = None,
    limit: int = 100,
) -> list[CampaignHistory]:
    q = select(CampaignHistory).order_by(CampaignHistory.timestamp.desc()).limit(limit)
    if campaign_id is not None:
        q = q.where(CampaignHistory.campaign_id == campaign_id)
    result = await db.execute(q)
    return list(result.scalars().all())


# ── Statistics ────────────────────────────────────────────────────────────────

async def get_campaign_stats(db: AsyncSession, campaign_id: int | None = None) -> dict:
    """Aggregate statistics from history and campaign_jobs."""
    job_q = select(CampaignJob.status, func.count(CampaignJob.id)).group_by(CampaignJob.status)
    if campaign_id:
        job_q = job_q.where(CampaignJob.campaign_id == campaign_id)
    rows = await db.execute(job_q)
    counts: dict[str, int] = {r[0]: r[1] for r in rows}
    total = sum(counts.values())
    completed = counts.get("COMPLETED", 0)
    failed = counts.get("FAILED", 0)

    # Average duration from history
    hist_q = select(func.avg(CampaignHistory.duration_s)).where(
        CampaignHistory.action == "COMPLETED"
    )
    if campaign_id:
        hist_q = hist_q.where(CampaignHistory.campaign_id == campaign_id)
    avg_dur = (await db.execute(hist_q)).scalar() or 0.0

    # Retry count
    retry_q = select(func.count(CampaignHistory.id)).where(CampaignHistory.action == "RETRIED")
    if campaign_id:
        retry_q = retry_q.where(CampaignHistory.campaign_id == campaign_id)
    retry_count = (await db.execute(retry_q)).scalar() or 0

    return {
        "total_jobs": total,
        "completed_jobs": completed,
        "failed_jobs": failed,
        "running_jobs": counts.get("RUNNING", 0),
        "waiting_jobs": counts.get("WAITING", 0) + counts.get("READY", 0),
        "cancelled_jobs": counts.get("CANCELLED", 0),
        "success_rate": round(completed / total * 100, 1) if total else 0.0,
        "avg_duration_s": round(avg_dur, 1),
        "retry_count": retry_count,
    }
