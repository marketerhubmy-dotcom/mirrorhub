import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.devices import registry
from app.devices.schemas import DeviceResponse
from app.services import scrcpy as scrcpy_svc

router = APIRouter(prefix="/mirror", tags=["mirror"])


class AdbConnectRequest(BaseModel):
    adb_address: str
    device_name: str | None = None


class MirrorStatus(BaseModel):
    device_id: str
    mirroring: bool


@router.post("/connect", response_model=DeviceResponse)
async def connect_adb_device(req: AdbConnectRequest, db: AsyncSession = Depends(get_db)):
    """Connect phone via ADB address and register in dashboard."""
    ok, msg = await scrcpy_svc.adb_connect(req.adb_address)
    if not ok:
        raise HTTPException(status_code=400, detail=f"ADB connect failed: {msg}")

    name = req.device_name or req.adb_address
    from app.devices.schemas import DeviceRegisterRequest
    data = DeviceRegisterRequest(
        device_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, req.adb_address)),
        device_name=name,
        battery=100,
        wifi=True,
    )
    device = await registry.register_device(db, data)
    device.adb_address = req.adb_address
    await db.commit()
    await db.refresh(device)
    return device


@router.post("/{device_id}/start", response_model=MirrorStatus)
async def start_mirror(device_id: str, db: AsyncSession = Depends(get_db)):
    device = await registry.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if not device.adb_address:
        raise HTTPException(status_code=400, detail="No ADB address for this device")

    ok, msg = await scrcpy_svc.start_mirror(device_id, device.adb_address, device.device_name)
    if not ok:
        raise HTTPException(status_code=502, detail=msg)
    return MirrorStatus(device_id=device_id, mirroring=True)


@router.delete("/{device_id}/stop", response_model=MirrorStatus)
async def stop_mirror(device_id: str):
    await scrcpy_svc.stop_mirror(device_id)
    return MirrorStatus(device_id=device_id, mirroring=False)


@router.get("/{device_id}/status", response_model=MirrorStatus)
async def mirror_status(device_id: str):
    return MirrorStatus(device_id=device_id, mirroring=scrcpy_svc.is_mirroring(device_id))
