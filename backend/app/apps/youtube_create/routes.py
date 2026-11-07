"""
YouTube Create plugin API.

Provides higher-level endpoints on top of /execution/jobs:
  POST /execute    — validate + multi-image + start via plugin
  POST /simulate   — dry-run: returns planned steps, no device interaction
  POST /validate   — validate job dict only
  GET  /config     — current plugin configuration values
  GET  /phases     — state machine phase definitions
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.registry import get_device
from app.models.database import get_db
from app.execution.device_session import is_device_busy, get_active_job
from .plugin import YouTubeCreatePlugin
from .constants import (
    GENERATION_TIMEOUT, EXPORT_TIMEOUT, LAUNCH_TIMEOUT, SHARE_TIMEOUT,
    RETRY_MAX, WAIT_POLL_INTERVAL, PREFERRED_RESOLUTION, PREFERRED_DURATION,
    PREFERRED_STYLE, MAX_IMAGES,
)
from .state import YouTubeCreatePhase

router = APIRouter(prefix="/apps/youtube_create", tags=["youtube_create_plugin"])

_plugin = YouTubeCreatePlugin()


class ExecuteRequest(BaseModel):
    device_id: str
    video_prompt: str
    image_path: str = ""
    image_paths: list[str] = []
    post_type: str = "draft"
    schedule_time: str | None = None
    content_job_id: int | None = None
    resolution: str = PREFERRED_RESOLUTION
    generation_timeout: int = GENERATION_TIMEOUT


class SimulateRequest(BaseModel):
    video_prompt: str
    image_path: str = ""
    image_paths: list[str] = []
    post_type: str = "draft"
    schedule_time: str | None = None
    resolution: str = PREFERRED_RESOLUTION
    generation_timeout: int = GENERATION_TIMEOUT


class ValidateRequest(BaseModel):
    video_prompt: str = ""
    image_path: str = ""
    image_paths: list[str] = []


@router.post("/execute")
async def execute(req: ExecuteRequest, db: AsyncSession = Depends(get_db)):
    """Start a YouTube Create execution via the plugin interface."""
    device = await get_device(db, req.device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.adb_address:
        raise HTTPException(400, "Device has no ADB address")
    if is_device_busy(req.device_id):
        active_id = get_active_job(req.device_id)
        raise HTTPException(409, f"Device busy — job {active_id} is running")

    job = req.model_dump()
    result = await _plugin.execute(job, device.adb_address, req.device_id)

    if not result.success:
        raise HTTPException(422, f"{result.code}: {result.reason}")

    return {
        "status": result.code,
        "reason": result.reason,
        "job_id": result.job_id,
        **result.data,
    }


@router.post("/simulate")
async def simulate(req: SimulateRequest):
    """Dry-run: validate + build workflow and return planned steps without executing."""
    job = req.model_dump()
    job["simulate"] = True

    result = await _plugin.execute(job, adb_address="", device_id="")
    if not result.success:
        raise HTTPException(422, f"{result.code}: {result.reason}")

    return {
        "status": result.code,
        "reason": result.reason,
        **result.data,
    }


@router.post("/validate")
async def validate_job(req: ValidateRequest):
    """Validate a job dict without any device interaction."""
    result = await _plugin.validate(req.model_dump())
    return {
        "success": result.success,
        "code": result.code,
        "reason": result.reason,
    }


@router.get("/config")
async def get_config():
    """Return the current plugin configuration."""
    return {
        "timeouts": {
            "launch": LAUNCH_TIMEOUT,
            "generation": GENERATION_TIMEOUT,
            "export": EXPORT_TIMEOUT,
            "share": SHARE_TIMEOUT,
        },
        "retry": {
            "max": RETRY_MAX,
            "poll_interval": WAIT_POLL_INTERVAL,
        },
        "media": {
            "preferred_resolution": PREFERRED_RESOLUTION,
            "preferred_duration": PREFERRED_DURATION,
            "preferred_style": PREFERRED_STYLE,
            "max_images": MAX_IMAGES,
        },
    }


@router.get("/phases")
async def get_phases():
    """Return the plugin's state machine phase definitions."""
    return {
        "phases": [p.value for p in YouTubeCreatePhase],
        "transitions": [
            {"from": YouTubeCreatePhase.INIT,           "to": YouTubeCreatePhase.OPEN_APP},
            {"from": YouTubeCreatePhase.OPEN_APP,       "to": YouTubeCreatePhase.CREATE_PROJECT},
            {"from": YouTubeCreatePhase.CREATE_PROJECT, "to": YouTubeCreatePhase.INPUT_PROMPT},
            {"from": YouTubeCreatePhase.INPUT_PROMPT,   "to": YouTubeCreatePhase.IMPORT_IMAGES},
            {"from": YouTubeCreatePhase.IMPORT_IMAGES,  "to": YouTubeCreatePhase.GENERATE},
            {"from": YouTubeCreatePhase.GENERATE,       "to": YouTubeCreatePhase.WAIT_GENERATION},
            {"from": YouTubeCreatePhase.WAIT_GENERATION,"to": YouTubeCreatePhase.EXPORT},
            {"from": YouTubeCreatePhase.EXPORT,         "to": YouTubeCreatePhase.SHARE},
            {"from": YouTubeCreatePhase.SHARE,          "to": YouTubeCreatePhase.DONE},
            {"from": "*",                               "to": YouTubeCreatePhase.FAILED},
        ],
    }
