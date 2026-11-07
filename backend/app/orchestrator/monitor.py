"""
Background device monitor.

Polls every HEALTH_POLL_INTERVAL seconds:
  1. ADB-ping all registered devices
  2. Update DeviceProfile status + health metrics
  3. On disconnect: trigger failover via allocator.migrate_jobs()
  4. Broadcast WebSocket events via manager
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.models.database import get_db
from app.models.device import Device
from sqlalchemy import select

from .health import check_device, _compute_score
from .models import (
    STATUS_IDLE, STATUS_OFFLINE, STATUS_DISCONNECTED,
    STATUS_BUSY, STATUS_RECOVERING, AVAILABLE_STATUSES,
)
from .repository import (
    get_or_create_profile,
    list_profiles,
    update_health_metrics,
    update_profile_status,
    increment_job_stats,
)

logger = logging.getLogger(__name__)

HEALTH_POLL_INTERVAL: float = 30.0  # seconds between full sweeps
_stop_event = asyncio.Event()


def stop_monitor() -> None:
    _stop_event.set()


async def run_monitor() -> None:
    """Main monitor loop. Run as an asyncio task from lifespan."""
    logger.info("Orchestrator monitor started (interval=%.0fs)", HEALTH_POLL_INTERVAL)
    _stop_event.clear()
    while not _stop_event.is_set():
        try:
            await _sweep()
        except Exception:
            logger.exception("Monitor sweep error")
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=HEALTH_POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def _sweep() -> None:
    """Poll all devices once and update DB state + trigger failover if needed."""
    async for db in get_db():
        # Get all registered devices that have an adb_address
        result = await db.execute(
            select(Device).where(Device.adb_address.isnot(None))
        )
        devices = list(result.scalars().all())

        # Kick off all health checks in parallel
        tasks = [
            asyncio.create_task(check_device(str(d.id), d.adb_address))
            for d in devices
        ]
        snapshots = await asyncio.gather(*tasks, return_exceptions=True)

        for device, snap in zip(devices, snapshots):
            if isinstance(snap, Exception):
                logger.debug("Health check error for %s: %s", device.id, snap)
                await _handle_unreachable(db, str(device.id))
                continue

            profile = await get_or_create_profile(db, str(device.id))
            was_available = profile.status in AVAILABLE_STATUSES

            if snap.reachable:
                new_status = STATUS_BUSY if profile.status == STATUS_BUSY else STATUS_IDLE
                await update_profile_status(db, str(device.id), new_status)
                await update_health_metrics(
                    db,
                    str(device.id),
                    latency_ms=snap.latency_ms,
                    performance_score=snap.performance_score,
                    resolution_w=snap.resolution_w,
                    resolution_h=snap.resolution_h,
                    android_version=snap.android_version,
                    ram_mb=snap.ram_mb,
                    storage_gb=snap.storage_gb,
                )
                if not was_available:
                    logger.info("Device %s back online (latency=%.0fms)", device.id, snap.latency_ms)
                    await _broadcast_event("device_connected", {
                        "device_id": str(device.id),
                        "status": new_status,
                        "latency_ms": snap.latency_ms,
                    })
            else:
                await _handle_unreachable(db, str(device.id))
                if was_available:
                    await _broadcast_event("device_lost", {
                        "device_id": str(device.id),
                    })


async def _handle_unreachable(db, device_id: str) -> None:
    """Mark device offline and migrate its pending jobs."""
    profile = await get_or_create_profile(db, device_id)
    prev = profile.status
    if prev in AVAILABLE_STATUSES or prev == STATUS_BUSY:
        await update_profile_status(db, device_id, STATUS_DISCONNECTED)
        logger.warning("Device %s unreachable — triggering failover", device_id)
        await _failover(db, device_id)


async def _failover(db, device_id: str) -> None:
    """
    Move WAITING/READY jobs away from a lost device.

    Imports allocator here to avoid circular import at module load time.
    """
    from .allocator import migrate_jobs
    from .repository import list_available_profiles

    available = await list_available_profiles(db)
    # Exclude the failed device itself
    candidates = [p for p in available if p.device_id != device_id]
    if not candidates:
        logger.warning("Failover: no other devices available to absorb jobs from %s", device_id)
        return

    # Pick highest-score candidate
    target = max(candidates, key=lambda p: p.performance_score)
    moved = await migrate_jobs(db, device_id, target.device_id)
    if moved:
        logger.info("Failover: moved %d jobs from %s → %s", moved, device_id, target.device_id)
        await _broadcast_event("failover", {
            "from_device_id": device_id,
            "to_device_id": target.device_id,
            "jobs_moved": moved,
        })


async def _broadcast_event(event_type: str, data: dict) -> None:
    try:
        import json
        from app.websocket.manager import manager
        payload = json.dumps({"event": event_type, "data": data})
        await manager.broadcast_orchestrator(payload)
    except Exception:
        pass  # WebSocket broadcast is best-effort
