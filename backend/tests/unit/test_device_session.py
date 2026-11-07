"""
CLAIM: Race condition fixed — try_claim_device is atomic via asyncio.Lock.

Verifies:
  1. Claiming a free device succeeds.
  2. Claiming an already-busy device fails immediately (no error).
  3. Two concurrent coroutines: exactly one wins, one loses.
  4. Clearing a device makes it claimable again.
  5. Module-level _active dict is isolated between tests by the autouse fixture.
"""
import asyncio

import pytest

from app.execution.device_session import (
    try_claim_device,
    clear_active_job,
    is_device_busy,
    get_active_job,
    set_active_job,
)


@pytest.mark.asyncio
async def test_claim_free_device_succeeds():
    ok = await try_claim_device("device-01", sentinel=100)
    assert ok is True


@pytest.mark.asyncio
async def test_claim_busy_device_fails():
    await try_claim_device("device-01", sentinel=100)
    ok2 = await try_claim_device("device-01", sentinel=200)
    assert ok2 is False


@pytest.mark.asyncio
async def test_claim_returns_false_does_not_modify_sentinel():
    """The first claim's sentinel must not be overwritten by a failed second claim."""
    await try_claim_device("device-01", sentinel=100)
    await try_claim_device("device-01", sentinel=999)   # should fail
    assert get_active_job("device-01") == 100


@pytest.mark.asyncio
async def test_clear_then_reclaim():
    await try_claim_device("device-01", sentinel=1)
    clear_active_job("device-01")
    ok = await try_claim_device("device-01", sentinel=2)
    assert ok is True


@pytest.mark.asyncio
async def test_is_device_busy_reflects_state():
    assert not is_device_busy("device-X")
    await try_claim_device("device-X", sentinel=5)
    assert is_device_busy("device-X")
    clear_active_job("device-X")
    assert not is_device_busy("device-X")


@pytest.mark.asyncio
async def test_set_active_job_updates_sentinel():
    await try_claim_device("device-01", sentinel=1)
    set_active_job("device-01", 42)
    assert get_active_job("device-01") == 42


@pytest.mark.asyncio
async def test_concurrent_claims_exactly_one_wins():
    """
    SCENARIO A: Two coroutines attempt to claim the same idle device simultaneously.

    Both tasks are released at the same instant via an asyncio.Event barrier.
    Expected: exactly one succeeds (True), exactly one is rejected (False).
    No duplicate assignment is made.
    """
    device_id = "shared-device"
    results: list[bool] = []
    barrier = asyncio.Event()
    ready_count = 0

    async def _claim(sentinel: int) -> None:
        nonlocal ready_count
        ready_count += 1
        if ready_count >= 2:
            barrier.set()
        else:
            await barrier.wait()
        result = await try_claim_device(device_id, sentinel)
        results.append(result)

    await asyncio.gather(_claim(1), _claim(2))

    assert len(results) == 2
    assert results.count(True) == 1,  "Exactly one task must claim the device"
    assert results.count(False) == 1, "Exactly one task must be rejected"
    # The winner's sentinel is stored; the loser's sentinel must not overwrite it
    job_id = get_active_job(device_id)
    assert job_id in (1, 2)


@pytest.mark.asyncio
async def test_concurrent_claims_multiple_devices_no_cross_contamination():
    """
    SCENARIO B (partial): Many devices, one claim each — no device gets double-claimed.
    """
    device_ids = [f"dev-{i}" for i in range(20)]
    results = await asyncio.gather(
        *[try_claim_device(dev, i) for i, dev in enumerate(device_ids)]
    )
    # Every claim should succeed (all devices were free)
    assert all(results), "All claims should succeed for different devices"
    # Each device should have exactly one sentinel
    for i, dev in enumerate(device_ids):
        assert get_active_job(dev) == i
