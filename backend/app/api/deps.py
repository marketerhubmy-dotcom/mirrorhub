"""Shared API helpers: device lookup and uniform error mapping."""
from __future__ import annotations

from contextlib import contextmanager

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices import registry
from app.models.database import get_db
from app.models.device import Device
from app.services.adb_client import AdbError, AdbMissing
from app.services.device_ops import OpError


async def get_device_or_404(device_id: str, db: AsyncSession = Depends(get_db)) -> Device:
    device = await registry.get_device(db, device_id)
    if device is None:
        raise HTTPException(404, "Peranti tidak dijumpai.")
    return device


async def get_online_device(device_id: str, db: AsyncSession = Depends(get_db)) -> Device:
    device = await get_device_or_404(device_id, db)
    if not device.adb_address:
        raise HTTPException(409, "Peranti ini tiada alamat ADB. Sambung semula dari Pairing Center.")
    if not device.is_online:
        hint = device.last_error or "Peranti offline."
        raise HTTPException(409, f"Peranti offline. {hint}")
    return device


@contextmanager
def adb_errors():
    """Translate service errors to HTTP errors with user-facing messages."""
    try:
        yield
    except OpError as exc:
        raise HTTPException(400, str(exc))
    except AdbMissing as exc:
        raise HTTPException(503, str(exc))
    except AdbError as exc:
        raise HTTPException(502, str(exc))
