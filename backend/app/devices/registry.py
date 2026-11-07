from datetime import datetime, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.devices.schemas import DeviceRegisterRequest, DeviceHeartbeat


async def register_device(db: AsyncSession, data: DeviceRegisterRequest) -> Device:
    result = await db.execute(select(Device).where(Device.device_id == data.device_id))
    device = result.scalar_one_or_none()

    if device is None:
        device = Device(
            device_id=data.device_id,
            device_name=data.device_name,
            battery=data.battery,
            wifi=data.wifi,
            is_online=True,
            last_seen=datetime.now(UTC),
        )
        db.add(device)
    else:
        device.device_name = data.device_name
        device.battery = data.battery
        device.wifi = data.wifi
        device.is_online = True
        device.last_seen = datetime.now(UTC)

    await db.commit()
    await db.refresh(device)
    return device


async def get_all_devices(db: AsyncSession) -> list[Device]:
    result = await db.execute(select(Device).order_by(Device.device_name))
    return list(result.scalars().all())


async def get_device(db: AsyncSession, device_id: str) -> Device | None:
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    return result.scalar_one_or_none()


async def update_heartbeat(db: AsyncSession, data: DeviceHeartbeat) -> Device | None:
    device = await get_device(db, data.device_id)
    if device is None:
        return None

    device.battery = data.battery
    device.wifi = data.wifi
    device.is_online = True
    device.last_seen = datetime.now(UTC)

    await db.commit()
    await db.refresh(device)
    return device


async def mark_offline(db: AsyncSession, device_id: str) -> None:
    device = await get_device(db, device_id)
    if device:
        device.is_online = False
        await db.commit()
