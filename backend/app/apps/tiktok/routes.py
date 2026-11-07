"""
TikTok Publisher plugin API.

Endpoints:
  POST /execute         — validate + build + start via plugin
  POST /simulate        — dry-run: returns planned steps, no device interaction
  POST /validate        — validate job dict only
  GET  /config          — current plugin configuration values
  GET  /phases          — state machine phase definitions
  GET  /products        — list all registered products
  POST /products        — add a product
  PUT  /products/{id}   — update a product
  DELETE /products/{id} — remove a product
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.registry import get_device
from app.models.database import get_db
from app.execution.device_session import is_device_busy, get_active_job
from .plugin import TikTokPlugin
from .product import product_manager
from .constants import (
    LAUNCH_TIMEOUT, UPLOAD_TIMEOUT, CAPTION_TIMEOUT, PRODUCT_TIMEOUT,
    PUBLISH_TIMEOUT, VERIFY_TIMEOUT,
    RETRY_MAX, POLL_INTERVAL, PUBLISH_DELAY, AUTO_CONFIRM,
    PREFERRED_UPLOAD_METHOD, MAX_CAPTION_LENGTH,
    ALLOWED_EXTENSIONS,
)
from .state import TikTokPhase

router = APIRouter(prefix="/apps/tiktok", tags=["tiktok_plugin"])

_plugin = TikTokPlugin()


# ── Request models ────────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    device_id: str
    video_path: str
    caption: str = ""
    hashtags: list[str] = []
    first_comment: str = ""
    product_id: str = ""
    product: dict | None = None
    post_type: str = "post_now"
    variables: dict[str, str] = {}
    content_job_id: int | None = None
    workflow_id: int | None = None


class SimulateRequest(BaseModel):
    video_path: str
    caption: str = ""
    hashtags: list[str] = []
    first_comment: str = ""
    product_id: str = ""
    product: dict | None = None
    post_type: str = "post_now"
    variables: dict[str, str] = {}
    workflow_id: int | None = None


class ValidateRequest(BaseModel):
    video_path: str = ""
    caption: str = ""
    hashtags: list[str] = []
    product_id: str = ""


class ProductCreateRequest(BaseModel):
    id: str
    name: str
    search_term: str
    sku: str = ""
    notes: str = ""


class ProductUpdateRequest(BaseModel):
    name: str | None = None
    search_term: str | None = None
    sku: str | None = None
    notes: str | None = None


# ── Plugin endpoints ──────────────────────────────────────────────────────────

@router.post("/execute")
async def execute(req: ExecuteRequest, db: AsyncSession = Depends(get_db)):
    """Start a TikTok publishing execution via the plugin interface."""
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
    """Return the current plugin configuration values."""
    return {
        "timeouts": {
            "launch": LAUNCH_TIMEOUT,
            "upload": UPLOAD_TIMEOUT,
            "caption": CAPTION_TIMEOUT,
            "product": PRODUCT_TIMEOUT,
            "publish": PUBLISH_TIMEOUT,
            "verify": VERIFY_TIMEOUT,
        },
        "retry": {
            "max": RETRY_MAX,
            "poll_interval": POLL_INTERVAL,
        },
        "publish": {
            "publish_delay": PUBLISH_DELAY,
            "auto_confirm": AUTO_CONFIRM,
            "preferred_upload_method": PREFERRED_UPLOAD_METHOD,
        },
        "caption": {
            "max_length": MAX_CAPTION_LENGTH,
            "allowed_video_formats": list(ALLOWED_EXTENSIONS),
        },
    }


@router.get("/phases")
async def get_phases():
    """Return the plugin state machine phase definitions."""
    return {
        "phases": [p.value for p in TikTokPhase],
        "transitions": [
            {"from": TikTokPhase.INIT,           "to": TikTokPhase.OPEN_APP},
            {"from": TikTokPhase.OPEN_APP,        "to": TikTokPhase.UPLOAD},
            {"from": TikTokPhase.UPLOAD,          "to": TikTokPhase.VIDEO_SELECTED},
            {"from": TikTokPhase.VIDEO_SELECTED,  "to": TikTokPhase.CAPTION},
            {"from": TikTokPhase.CAPTION,         "to": TikTokPhase.PRODUCT},
            {"from": TikTokPhase.PRODUCT,         "to": TikTokPhase.VALIDATION},
            {"from": TikTokPhase.VALIDATION,      "to": TikTokPhase.PUBLISH},
            {"from": TikTokPhase.PUBLISH,         "to": TikTokPhase.VERIFY},
            {"from": TikTokPhase.VERIFY,          "to": TikTokPhase.DONE},
            {"from": "*",                         "to": TikTokPhase.FAILED},
        ],
    }


# ── Product Manager endpoints ─────────────────────────────────────────────────

@router.get("/products")
async def list_products():
    """List all registered TikTok Shop products."""
    return {"products": [p.to_dict() for p in product_manager.list_all()]}


@router.post("/products", status_code=201)
async def add_product(req: ProductCreateRequest):
    """Register a new TikTok Shop product."""
    if product_manager.get(req.id):
        raise HTTPException(409, f"Product '{req.id}' already exists")
    p = product_manager.add(
        req.id,
        name=req.name,
        search_term=req.search_term,
        sku=req.sku,
        notes=req.notes,
    )
    return p.to_dict()


@router.put("/products/{product_id}")
async def update_product(product_id: str, req: ProductUpdateRequest):
    """Update an existing product's fields."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    p = product_manager.update(product_id, **updates)
    if not p:
        raise HTTPException(404, f"Product '{product_id}' not found")
    return p.to_dict()


@router.delete("/products/{product_id}")
async def delete_product(product_id: str):
    """Remove a product from the registry."""
    removed = product_manager.remove(product_id)
    if not removed:
        raise HTTPException(404, f"Product '{product_id}' not found")
    return {"deleted": product_id}
