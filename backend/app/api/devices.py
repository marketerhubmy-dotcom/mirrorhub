from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.devices import registry
from app.devices.schemas import DeviceRegisterRequest, DeviceResponse, DeviceHeartbeat

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register", response_model=DeviceResponse)
async def register_device(data: DeviceRegisterRequest, db: AsyncSession = Depends(get_db)):
    device = await registry.register_device(db, data)
    return device


@router.get("", response_model=list[DeviceResponse])
async def list_devices(db: AsyncSession = Depends(get_db)):
    return await registry.get_all_devices(db)


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)):
    device = await registry.get_device(db, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.post("/heartbeat", response_model=DeviceResponse)
async def heartbeat(data: DeviceHeartbeat, db: AsyncSession = Depends(get_db)):
    device = await registry.update_heartbeat(db, data)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found — register first")
    return device
