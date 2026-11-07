"""
Device session registry — tracks which execution job has claimed each device.

All mutations go through try_claim_device / clear_active_job so that
the dispatcher can never double-assign a device between two concurrent ticks.

The asyncio.Lock serialises the check-and-set inside try_claim_device.
Read-only helpers (is_device_busy, get_active_job) are lock-free because
FastAPI runs on a single asyncio event loop thread and dict reads are atomic.
"""
import asyncio

_active: dict[str, int] = {}  # device_id -> execution_job_id (or sentinel campaign_job_id)
_lock = asyncio.Lock()


async def try_claim_device(device_id: str, sentinel: int) -> bool:
    """
    Atomically check-and-claim a device.

    Returns True and marks the device busy when it was free.
    Returns False without side-effects when already busy.

    The caller must call clear_active_job() if the subsequent dispatch fails
    before set_active_job() is called by the execution engine.
    """
    async with _lock:
        if device_id in _active:
            return False
        _active[device_id] = sentinel
        return True


def is_device_busy(device_id: str) -> bool:
    return device_id in _active


def get_active_job(device_id: str) -> int | None:
    return _active.get(device_id)


def set_active_job(device_id: str, job_id: int) -> None:
    """Update an already-claimed device slot with the real execution job id."""
    _active[device_id] = job_id


def clear_active_job(device_id: str) -> None:
    _active.pop(device_id, None)
