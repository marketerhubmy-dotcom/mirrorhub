"""
Campaign Scheduler & Queue Engine API.

Campaign CRUD:
  GET    /campaigns
  POST   /campaigns
  GET    /campaigns/{id}
  PUT    /campaigns/{id}
  DELETE /campaigns/{id}
  POST   /campaigns/{id}/start
  POST   /campaigns/{id}/pause
  POST   /campaigns/{id}/resume
  POST   /campaigns/{id}/cancel
  GET    /campaigns/{id}/jobs
  GET    /campaigns/{id}/validate
  GET    /campaigns/{id}/estimate
  GET    /campaigns/{id}/schedule
  GET    /campaigns/{id}/history
  GET    /campaigns/{id}/stats

Campaign Job CRUD:
  POST   /campaigns/jobs
  GET    /campaigns/jobs/{id}
  PUT    /campaigns/jobs/{id}
  DELETE /campaigns/jobs/{id}
  POST   /campaigns/jobs/{id}/pause
  POST   /campaigns/jobs/{id}/resume
  POST   /campaigns/jobs/{id}/cancel
  POST   /campaigns/jobs/{id}/retry
  POST   /campaigns/jobs/{id}/simulate

Queue:
  GET    /campaigns/queue
  POST   /campaigns/queue/pause
  POST   /campaigns/queue/resume
  POST   /campaigns/queue/reorder
  DELETE /campaigns/queue/{entry_id}

History & Stats:
  GET    /campaigns/history
  GET    /campaigns/stats
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from . import repository as repo, planner
from .queue import queue_engine
from .schemas import (
    CampaignCreate, CampaignUpdate,
    CampaignJobCreate, CampaignJobUpdate,
    CampaignStartRequest, QueueReorderRequest,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# ── Campaign CRUD ─────────────────────────────────────────────────────────────

@router.get("")
async def list_campaigns(db: AsyncSession = Depends(get_db)):
    campaigns = await repo.list_campaigns(db)
    return [c.to_dict() for c in campaigns]


@router.post("", status_code=201)
async def create_campaign(data: CampaignCreate, db: AsyncSession = Depends(get_db)):
    c = await repo.create_campaign(db, data)
    return c.to_dict()


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    c = await repo.get_campaign(db, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")
    return c.to_dict()


@router.put("/{campaign_id}")
async def update_campaign(campaign_id: int, data: CampaignUpdate, db: AsyncSession = Depends(get_db)):
    c = await repo.update_campaign(db, campaign_id, data)
    if not c:
        raise HTTPException(404, "Campaign not found")
    return c.to_dict()


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    ok = await repo.delete_campaign(db, campaign_id)
    if not ok:
        raise HTTPException(404, "Campaign not found")


# ── Campaign control ──────────────────────────────────────────────────────────

@router.post("/{campaign_id}/start")
async def start_campaign(
    campaign_id: int,
    req: CampaignStartRequest,
    db: AsyncSession = Depends(get_db),
):
    """Enqueue all WAITING CampaignJobs and set campaign to RUNNING."""
    c = await repo.get_campaign(db, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")
    if c.status in ("RUNNING",):
        raise HTTPException(409, "Campaign is already running")

    # Validate first
    validation = await planner.validate_campaign(campaign_id)
    if not validation["valid"]:
        raise HTTPException(422, {"errors": validation["errors"]})

    jobs = await repo.list_campaign_jobs(db, campaign_id)
    enqueued = 0
    for j in jobs:
        if j.status == "WAITING":
            if req.simulate:
                j.job_config_json = json.dumps({
                    **json.loads(j.job_config_json or "{}"),
                    "simulate": True,
                })
                await db.commit()
            await queue_engine.add(j.id, priority=j.priority)
            enqueued += 1

    c.status = "RUNNING"
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()

    await repo.record_history(db, "STARTED", campaign_id=campaign_id,
                              detail=f"Enqueued {enqueued} jobs")
    return {"status": "running", "enqueued": enqueued, "simulate": req.simulate}


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    c = await repo.get_campaign(db, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")

    # Pause all active queue entries for this campaign
    jobs = await repo.list_campaign_jobs(db, campaign_id)
    paused = 0
    for j in jobs:
        entry = await repo.get_queue_entry_by_job(db, j.id)
        if entry and entry.status in ("WAITING", "READY"):
            await queue_engine.pause_entry(entry.id)
            paused += 1

    c.status = "PAUSED"
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await repo.record_history(db, "PAUSED", campaign_id=campaign_id)
    return {"status": "paused", "paused_entries": paused}


@router.post("/{campaign_id}/resume")
async def resume_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    c = await repo.get_campaign(db, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")

    jobs = await repo.list_campaign_jobs(db, campaign_id)
    resumed = 0
    for j in jobs:
        entry = await repo.get_queue_entry_by_job(db, j.id)
        if entry and entry.status == "PAUSED":
            await queue_engine.resume_entry(entry.id)
            resumed += 1

    c.status = "RUNNING"
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await repo.record_history(db, "RESUMED", campaign_id=campaign_id)
    return {"status": "running", "resumed_entries": resumed}


@router.post("/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    c = await repo.get_campaign(db, campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")

    jobs = await repo.list_campaign_jobs(db, campaign_id)
    cancelled = 0
    for j in jobs:
        entry = await repo.get_queue_entry_by_job(db, j.id)
        if entry and entry.status not in ("COMPLETED", "FAILED", "CANCELLED"):
            await queue_engine.cancel_entry(entry.id)
            await repo.set_campaign_job_status(db, j.id, "CANCELLED")
            cancelled += 1

    c.status = "CANCELLED"
    c.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await repo.record_history(db, "CANCELLED", campaign_id=campaign_id)
    return {"status": "cancelled", "cancelled_jobs": cancelled}


# ── Campaign info ─────────────────────────────────────────────────────────────

@router.get("/{campaign_id}/jobs")
async def list_jobs(campaign_id: int, db: AsyncSession = Depends(get_db)):
    jobs = await repo.list_campaign_jobs(db, campaign_id)
    return [j.to_dict() for j in jobs]


@router.get("/{campaign_id}/validate")
async def validate_campaign(campaign_id: int):
    return await planner.validate_campaign(campaign_id)


@router.get("/{campaign_id}/estimate")
async def estimate(campaign_id: int):
    return await planner.estimate_remaining_time(campaign_id)


@router.get("/{campaign_id}/schedule")
async def schedule_preview(campaign_id: int):
    return await planner.get_schedule_preview(campaign_id)


@router.get("/{campaign_id}/history")
async def get_history(campaign_id: int, db: AsyncSession = Depends(get_db)):
    history = await repo.list_history(db, campaign_id=campaign_id)
    return [h.to_dict() for h in history]


@router.get("/{campaign_id}/stats")
async def campaign_stats(campaign_id: int, db: AsyncSession = Depends(get_db)):
    return await repo.get_campaign_stats(db, campaign_id=campaign_id)


# ── Campaign Job CRUD ─────────────────────────────────────────────────────────

@router.post("/jobs", status_code=201)
async def create_job(data: CampaignJobCreate, db: AsyncSession = Depends(get_db)):
    c = await repo.get_campaign(db, data.campaign_id)
    if not c:
        raise HTTPException(404, "Campaign not found")
    job = await repo.create_campaign_job(db, data)
    return job.to_dict()


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await repo.get_campaign_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


@router.put("/jobs/{job_id}")
async def update_job(job_id: int, data: CampaignJobUpdate, db: AsyncSession = Depends(get_db)):
    job = await repo.update_campaign_job(db, job_id, data)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await repo.get_campaign_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    # Cancel queue entry if active
    entry = await repo.get_queue_entry_by_job(db, job_id)
    if entry and entry.status not in ("COMPLETED", "FAILED", "CANCELLED"):
        await queue_engine.cancel_entry(entry.id)
    await db.delete(job)
    await db.commit()


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: int, db: AsyncSession = Depends(get_db)):
    entry = await repo.get_queue_entry_by_job(db, job_id)
    if not entry:
        raise HTTPException(404, "No queue entry for this job")
    await queue_engine.pause_entry(entry.id)
    await repo.set_campaign_job_status(db, job_id, "PAUSED")
    return {"status": "paused"}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: int, db: AsyncSession = Depends(get_db)):
    entry = await repo.get_queue_entry_by_job(db, job_id)
    if not entry:
        raise HTTPException(404, "No queue entry for this job")
    await queue_engine.resume_entry(entry.id)
    await repo.set_campaign_job_status(db, job_id, "READY")
    return {"status": "ready"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: int, db: AsyncSession = Depends(get_db)):
    entry = await repo.get_queue_entry_by_job(db, job_id)
    if entry:
        await queue_engine.cancel_entry(entry.id)
    await repo.set_campaign_job_status(db, job_id, "CANCELLED")
    return {"status": "cancelled"}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await repo.get_campaign_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("FAILED", "CANCELLED"):
        raise HTTPException(409, f"Cannot retry job in status {job.status}")

    job.status = "WAITING"
    job.retry_count = 0
    job.error = None
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    entry_id = await queue_engine.add(job_id, priority=job.priority)
    return {"status": "waiting", "entry_id": entry_id}


@router.post("/jobs/{job_id}/simulate")
async def simulate_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await repo.get_campaign_job(db, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    from . import executor as camp_exec
    result = await camp_exec.simulate(job)
    return {
        "success": result.success,
        "code": result.code,
        "reason": result.reason,
        **result.data,
    }


# ── Queue management ──────────────────────────────────────────────────────────

@router.get("/queue")
async def get_queue(db: AsyncSession = Depends(get_db)):
    entries = await repo.list_active_queue(db)
    result = []
    for e in entries:
        cj = await repo.get_campaign_job(db, e.campaign_job_id)
        result.append({**e.to_dict(), "campaign_job": cj.to_dict() if cj else None})
    return {
        "queue": result,
        "counts": queue_engine.counts(),
        "paused": queue_engine.is_paused,
    }


@router.get("/queue/all")
async def get_full_queue(db: AsyncSession = Depends(get_db)):
    entries = await repo.list_queue(db)
    return [e.to_dict() for e in entries]


@router.post("/queue/pause")
async def pause_queue():
    queue_engine.pause_queue()
    return {"status": "paused"}


@router.post("/queue/resume")
async def resume_queue():
    queue_engine.resume_queue()
    return {"status": "running"}


@router.post("/queue/reorder")
async def reorder_queue(req: QueueReorderRequest):
    await queue_engine.reorder(req.campaign_job_id, req.new_order)
    return {"status": "reordered"}


@router.delete("/queue/{entry_id}")
async def remove_from_queue(entry_id: int):
    await queue_engine.cancel_entry(entry_id)
    return {"status": "cancelled", "entry_id": entry_id}


# ── Global history & stats ────────────────────────────────────────────────────

@router.get("/history")
async def get_all_history(db: AsyncSession = Depends(get_db)):
    history = await repo.list_history(db)
    return [h.to_dict() for h in history]


@router.get("/stats")
async def global_stats(db: AsyncSession = Depends(get_db)):
    return await repo.get_campaign_stats(db)
