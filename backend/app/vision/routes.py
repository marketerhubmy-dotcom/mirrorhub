from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.registry import get_device
from app.models.database import get_db
from .analyzer import analyze_screen, wait_until
from .cache import get as get_cached, get_history, clear
from .providers import list_providers
from .screenshot import capture

router = APIRouter(prefix="/vision", tags=["vision"])


class WaitRequest(BaseModel):
    screen: str | None = None
    button: str | None = None
    loading: bool | None = None
    timeout: int = 30
    poll_interval: float = 3.0
    provider: str = "uiautomator"


async def _resolve_device(device_id: str, db: AsyncSession):
    device = await get_device(db, device_id)
    if not device:
        raise HTTPException(404, "Device not found")
    if not device.adb_address:
        raise HTTPException(400, "Device has no ADB address")
    return device


@router.post("/{device_id}/analyze")
async def analyze(
    device_id: str,
    provider: str = Query("uiautomator"),
    db: AsyncSession = Depends(get_db),
):
    """Capture screenshot + run full vision pipeline."""
    device = await _resolve_device(device_id, db)
    analysis = await analyze_screen(
        adb_address=device.adb_address,
        device_id=device_id,
        provider=provider,
    )
    return analysis.to_dict()


@router.get("/{device_id}/screenshot")
async def screenshot(device_id: str, db: AsyncSession = Depends(get_db)):
    """Capture screenshot only (no analysis). Returns web path."""
    device = await _resolve_device(device_id, db)
    cap = await capture(device.adb_address, device_id)
    if not cap.web_path:
        raise HTTPException(500, "Screenshot failed")
    return {
        "web_path": cap.web_path,
        "width": cap.width,
        "height": cap.height,
        "timestamp": cap.timestamp.isoformat(),
    }


@router.get("/{device_id}/state")
async def current_state(device_id: str):
    """Return latest cached ScreenAnalysis (no new capture)."""
    cached = get_cached(device_id)
    if not cached:
        raise HTTPException(404, "No cached state — call /analyze first")
    return cached.to_dict()


@router.get("/{device_id}/history")
async def history(device_id: str, n: int = Query(20, ge=1, le=20)):
    """Return last N ScreenAnalysis objects from in-memory history."""
    return [a.to_dict() for a in get_history(device_id, n)]


@router.post("/{device_id}/wait")
async def wait(
    device_id: str,
    req: WaitRequest,
    db: AsyncSession = Depends(get_db),
):
    """Wait until screen/button/loading conditions are met."""
    device = await _resolve_device(device_id, db)
    analysis = await wait_until(
        adb_address=device.adb_address,
        device_id=device_id,
        screen=req.screen,
        button=req.button,
        loading=req.loading,
        timeout=req.timeout,
        poll_interval=req.poll_interval,
        provider=req.provider,
    )
    return analysis.to_dict()


@router.post("/{device_id}/ocr")
async def ocr_only(device_id: str, db: AsyncSession = Depends(get_db)):
    """Run OCR only (no screenshot — uses last captured state of device screen)."""
    device = await _resolve_device(device_id, db)
    from .ocr import extract
    result = await extract(device.adb_address)
    return {
        "visible_text": result.visible_text,
        "buttons": [b.to_dict() for b in result.buttons],
        "editable_fields": result.editable_fields,
        "dialogs": result.dialogs,
    }


@router.delete("/{device_id}/cache")
async def clear_cache(device_id: str):
    """Clear in-memory vision cache for this device."""
    clear(device_id)
    return {"cleared": device_id}


@router.get("/providers")
async def providers():
    """List available vision providers."""
    return {"providers": list_providers()}
