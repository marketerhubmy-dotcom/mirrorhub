from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.registry import get_device
from app.models.database import get_db
from .device_session import get_active_job, is_device_busy
from .models import ExecutionJob
from .workflow_builder import build_youtube_create_workflow
from . import executor

router = APIRouter(prefix="/execution", tags=["execution"])


class StartRequest(BaseModel):
    device_id: str
    content_job_id: int | None = None
    video_prompt: str
    image_path: str
    platform: str = "youtube_create"
    post_type: str = "draft"
    schedule_time: str | None = None


@router.post("/jobs")
async def start_execution(req: StartRequest, db: AsyncSession = Depends(get_db)):
    device = await get_device(db, req.device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.adb_address:
        raise HTTPException(400, "Device has no ADB address")
    if is_device_busy(req.device_id):
        active_id = get_active_job(req.device_id)
        raise HTTPException(409, f"Device busy — job {active_id} is running")

    db_job = ExecutionJob(
        content_job_id=req.content_job_id,
        device_id=req.device_id,
        adb_address=device.adb_address,
        platform=req.platform,
        post_type=req.post_type,
        schedule_time=req.schedule_time,
        video_prompt=req.video_prompt,
        image_path=req.image_path,
        status="STARTING",
    )
    db.add(db_job)
    await db.commit()
    await db.refresh(db_job)

    steps = build_youtube_create_workflow(
        script=req.video_prompt,
        image_local_path=req.image_path,
        post_type=req.post_type,
        schedule_time=req.schedule_time,
        device_id=req.device_id,
    )

    await executor.start_execution(
        job_id=db_job.id,
        device_id=req.device_id,
        adb_address=device.adb_address,
        steps=steps,
    )
    return {"status": "started", "job_id": db_job.id, "total_steps": len(steps)}


@router.get("/jobs")
async def list_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ExecutionJob).order_by(ExecutionJob.created_at.desc()).limit(50)
    )
    return [j.to_dict() for j in result.scalars().all()]


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    state = executor.get_state(job_id)
    if state:
        return state.to_dict()
    job = await db.get(ExecutionJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: int):
    engine = executor.get_engine(job_id)
    if not engine:
        raise HTTPException(404, "Job not active")
    engine.pause()
    return {"status": "paused", "job_id": job_id}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: int):
    engine = executor.get_engine(job_id)
    if not engine:
        raise HTTPException(404, "Job not active")
    engine.resume()
    return {"status": "resumed", "job_id": job_id}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: int):
    engine = executor.get_engine(job_id)
    if not engine:
        raise HTTPException(404, "Job not active")
    engine.cancel()
    return {"status": "cancelled", "job_id": job_id}


@router.get("/active")
async def active_executions():
    from .device_session import _active
    return {"active": _active}
