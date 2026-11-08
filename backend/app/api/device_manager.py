"""
Device Manager API (extends /devices).

PATCH  /devices/{id}                 rename, tags, group, notes
DELETE /devices/{id}?confirm=true    forget the device (DB row only; the phone is untouched)
POST   /devices/{id}/refresh         re-read model/battery/storage/screen
POST   /devices/{id}/reconnect       wireless re-connect
POST   /devices/{id}/disconnect      wireless disconnect (suppresses auto-reconnect)
POST   /devices/{id}/screenshot      PNG
POST   /devices/{id}/record/start|stop
GET    /recordings/{name}            download a finished recording
"""
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import adb_errors, get_device_or_404, get_online_device
from app.core import runtime_paths as rp
from app.devices.lifecycle import get_monitor
from app.models.database import get_db
from app.models.device import Device
from app.services import adb_client, device_ops
from app.services.device_info import fetch_info
from app.services.scrcpy_stream import stream_manager

router = APIRouter(tags=["device-manager"])

_REC_NAME = re.compile(r"^[A-Za-z0-9._-]{1,200}\.mp4$")


class DevicePatch(BaseModel):
    device_name: str | None = Field(None, min_length=1, max_length=128)
    tags: list[str] | None = None
    group_name: str | None = Field(None, max_length=64)
    notes: str | None = Field(None, max_length=2000)


def serialize(d: Device) -> dict:
    try:
        tags = json.loads(d.tags or "[]")
    except json.JSONDecodeError:
        tags = []
    return {
        "device_id": d.device_id, "device_name": d.device_name, "battery": d.battery, "wifi": d.wifi,
        "is_online": d.is_online, "adb_address": d.adb_address,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "hw_serial": d.hw_serial, "model": d.model, "manufacturer": d.manufacturer,
        "android_version": d.android_version, "sdk": d.sdk, "transport": d.transport, "state": d.state,
        "storage_total_mb": d.storage_total_mb, "storage_free_mb": d.storage_free_mb,
        "screen_w": d.screen_w, "screen_h": d.screen_h, "tags": tags, "group_name": d.group_name,
        "notes": d.notes, "last_error": d.last_error,
    }


@router.patch("/devices/{device_id}")
async def patch_device(device_id: str, patch: DevicePatch, device: Device = Depends(get_device_or_404),
                       db: AsyncSession = Depends(get_db)):
    if patch.device_name is not None:
        name = patch.device_name.strip()
        if not name:
            raise HTTPException(400, "Nama tidak boleh kosong.")
        device.device_name = name
    if patch.tags is not None:
        clean = sorted({t.strip()[:32] for t in patch.tags if t and t.strip()})[:20]
        device.tags = json.dumps(clean)
    if patch.group_name is not None:
        device.group_name = patch.group_name.strip()
    if patch.notes is not None:
        device.notes = patch.notes
    await db.commit()
    await db.refresh(device)
    return serialize(device)


@router.delete("/devices/{device_id}")
async def forget_device(device_id: str, confirm: bool = Query(False), device: Device = Depends(get_device_or_404),
                        db: AsyncSession = Depends(get_db)):
    if not confirm:
        raise HTTPException(400, "Tambah ?confirm=true untuk mengesahkan. Hanya rekod dalam Mirrorhub dipadam; telefon tidak terjejas.")
    if device.adb_address:
        get_monitor().suppress_reconnect(device.adb_address)
    await stream_manager.stop_device(device_id)
    await db.delete(device)
    await db.commit()
    return {"ok": True}


@router.post("/devices/{device_id}/refresh")
async def refresh_device(device: Device = Depends(get_online_device), db: AsyncSession = Depends(get_db)):
    with adb_errors():
        info = await fetch_info(device.adb_address)
    if info.model:
        device.model = info.model
    device.manufacturer = info.manufacturer or device.manufacturer
    device.android_version = info.android_version or device.android_version
    device.sdk = info.sdk or device.sdk
    if info.battery >= 0:
        device.battery = info.battery
    device.storage_total_mb = info.storage_total_mb or device.storage_total_mb
    device.storage_free_mb = info.storage_free_mb or device.storage_free_mb
    device.screen_w = info.screen_w or device.screen_w
    device.screen_h = info.screen_h or device.screen_h
    await db.commit()
    await db.refresh(device)
    return serialize(device) | {"wifi_ip": info.wifi_ip, "charging": info.charging, "battery_temp_c": info.battery_temp_c}


@router.post("/devices/{device_id}/reconnect")
async def reconnect_device(device: Device = Depends(get_device_or_404)):
    if not device.adb_address or not adb_client.is_wifi_reconnectable(device.adb_address):
        raise HTTPException(400, "Sambung semula automatik hanya untuk peranti WiFi. Untuk USB, cabut dan pasang semula kabel.")
    with adb_errors():
        ok, msg = await get_monitor().reconnect_now(device.adb_address)
    if ok:
        await get_monitor().tick()
    return {"ok": ok, "message": msg}


@router.post("/devices/{device_id}/disconnect")
async def disconnect_device(device: Device = Depends(get_device_or_404)):
    if not device.adb_address or not adb_client.IP_PORT_RE.match(device.adb_address):  # mDNS routes are managed by adb itself
        raise HTTPException(400, "Hanya peranti WiFi boleh diputuskan dari sini.")
    get_monitor().suppress_reconnect(device.adb_address)
    with adb_errors():
        ok, msg = await adb_client.disconnect(device.adb_address)
    return {"ok": ok, "message": msg}


@router.post("/devices/{device_id}/screenshot")
async def take_screenshot(device: Device = Depends(get_online_device)):
    with adb_errors():
        png = await device_ops.screenshot(device.adb_address)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", device.device_name)[:40] or "device"
    return Response(png, media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.png"'})


@router.post("/devices/{device_id}/record/start")
async def record_start(device: Device = Depends(get_online_device), seconds: int | None = Query(None, ge=5, le=180)):
    from app.services import preferences
    seconds = seconds or int(preferences.get("record_seconds"))   # default comes from the saved preference
    with adb_errors():
        remote = await device_ops.record_start(device.adb_address, seconds)
    return {"ok": True, "remote": remote, "max_seconds": seconds}


@router.post("/devices/{device_id}/record/stop")
async def record_stop(device: Device = Depends(get_online_device)):
    with adb_errors():
        local = await device_ops.record_stop(device.adb_address)
    return {"ok": True, "name": local.name, "url": f"/api/v1/recordings/{local.name}"}


@router.get("/recordings/{name}")
async def download_recording(name: str):
    if not _REC_NAME.match(name):
        raise HTTPException(400, "Nama tidak sah.")
    p: Path = rp.data_dir() / "recordings" / name
    if not p.is_file():
        raise HTTPException(404, "Rakaman tidak dijumpai.")
    return FileResponse(p, media_type="video/mp4", filename=name)
