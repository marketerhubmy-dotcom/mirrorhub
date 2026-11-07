"""
Concurrency test suite — deterministic race condition proofs.

SCENARIO A: Two tasks claim the same device simultaneously — exactly one wins.
SCENARIO B: Multiple jobs against multiple devices — no double-assignment.
SCENARIO C: Device disconnects during assignment — no partial state remains.
SCENARIO D: Two scheduler ticks overlap — no duplicate dispatch.

All tests use asyncio.Event / asyncio.Barrier for deterministic synchronization.
No real phone required. No real AI API required.
"""
import asyncio
from typing import Optional

import pytest

from app.execution.device_session import (
    try_claim_device,
    clear_active_job,
    get_active_job,
    is_device_busy,
)


# ── SCENARIO A ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_a_only_one_wins_single_device():
    """
    Scenario A: Two concurrent claim attempts on the same idle device.

    An asyncio.Event is used to hold both tasks at the gate, then releases
    them simultaneously. After both settle, exactly one must have succeeded.
    """
    DEVICE_ID = "concurrent-device-A"
    gate = asyncio.Event()
    results: list[tuple[int, bool]] = []   # (sentinel, success)

    async def _race(sentinel: int) -> None:
        await gate.wait()   # wait for the start signal
        ok = await try_claim_device(DEVICE_ID, sentinel)
        results.append((sentinel, ok))

    tasks = [asyncio.create_task(_race(i)) for i in range(2)]
    gate.set()                              # release all at once
    await asyncio.gather(*tasks)

    winners = [s for s, ok in results if ok]
    losers  = [s for s, ok in results if not ok]

    assert len(winners) == 1, f"Expected 1 winner, got {len(winners)}: {winners}"
    assert len(losers)  == 1, f"Expected 1 loser, got {len(losers)}: {losers}"

    # The stored job ID must match the winning sentinel
    stored = get_active_job(DEVICE_ID)
    assert stored == winners[0], (
        f"Stored job {stored} does not match the winning sentinel {winners[0]}"
    )


@pytest.mark.asyncio
async def test_scenario_a_repeated_10_rounds():
    """
    Run Scenario A 10 rounds to catch non-deterministic lock failures.
    Each round uses a fresh device ID. In every round, exactly one task wins.
    """
    for round_num in range(10):
        device_id = f"race-device-r{round_num}"
        gate = asyncio.Event()
        results: list[bool] = []

        async def _race(sentinel: int) -> None:
            await gate.wait()
            results.append(await try_claim_device(device_id, sentinel))

        tasks = [asyncio.create_task(_race(i)) for i in range(5)]
        gate.set()
        await asyncio.gather(*tasks)

        wins = results.count(True)
        assert wins == 1, (
            f"Round {round_num}: expected 1 winner among 5 tasks, got {wins}"
        )


# ── SCENARIO B ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_b_multiple_jobs_multiple_devices():
    """
    Scenario B: N jobs compete for N devices simultaneously.

    Each device should be claimed by exactly one job.
    No device should be assigned more than once.
    """
    N = 10
    DEVICES = [f"b-device-{i}" for i in range(N)]
    gate = asyncio.Event()
    claims: dict[str, list[int]] = {d: [] for d in DEVICES}

    async def _worker(job_id: int) -> None:
        await gate.wait()
        # Each worker tries to claim ALL devices; should only get one per device
        for device_id in DEVICES:
            ok = await try_claim_device(device_id, job_id)
            if ok:
                claims[device_id].append(job_id)

    # N*2 workers, only N devices — each device should be claimed exactly once
    tasks = [asyncio.create_task(_worker(i)) for i in range(N * 2)]
    gate.set()
    await asyncio.gather(*tasks)

    for device_id, winners in claims.items():
        assert len(winners) == 1, (
            f"{device_id} was claimed {len(winners)} times: {winners}"
        )


# ── SCENARIO C ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_c_disconnect_during_claim_leaves_no_partial_state():
    """
    Scenario C: A device is claimed, then 'disconnects' (clear_active_job is called)
    mid-flow. The next claim attempt must succeed cleanly with no stale state.
    """
    DEVICE_ID = "disconnect-device-C"
    disconnect_event = asyncio.Event()
    reassign_event = asyncio.Event()
    results: dict[str, Optional[bool]] = {"first": None, "reassign": None}

    async def _original_job() -> None:
        ok = await try_claim_device(DEVICE_ID, sentinel=100)
        results["first"] = ok
        await disconnect_event.wait()   # hold the job
        clear_active_job(DEVICE_ID)     # simulate disconnect
        reassign_event.set()

    async def _recovery_job() -> None:
        await reassign_event.wait()     # wait for disconnect + clear
        results["reassign"] = await try_claim_device(DEVICE_ID, sentinel=200)

    await asyncio.gather(_original_job(), _recovery_job(),
                         _trigger_disconnect(disconnect_event))

    assert results["first"] is True, "Original job failed to claim device"
    assert results["reassign"] is True, (
        "Recovery job failed to claim device after disconnect — stale state persists"
    )
    assert get_active_job(DEVICE_ID) == 200


async def _trigger_disconnect(event: asyncio.Event):
    """Helper: triggers the disconnect event after a brief moment."""
    await asyncio.sleep(0.01)
    event.set()


# ── SCENARIO D ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_d_overlapping_scheduler_ticks_no_duplicate_dispatch():
    """
    Scenario D: Two scheduler ticks run concurrently against the same PENDING job.

    The dispatch table acts as the lock. Only one tick should dispatch; the other
    should see the job as already claimed and skip it.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    dispatched_jobs: list[int] = []

    async def _fake_dispatch(job_id: int, device_id: str) -> None:
        """Simulates the critical section: claim then dispatch."""
        ok = await try_claim_device(device_id, sentinel=job_id)
        if ok:
            dispatched_jobs.append(job_id)

    gate = asyncio.Event()

    async def _tick() -> None:
        await gate.wait()
        await _fake_dispatch(job_id=1, device_id="d-device-D")

    tick1 = asyncio.create_task(_tick())
    tick2 = asyncio.create_task(_tick())
    gate.set()
    await asyncio.gather(tick1, tick2)

    assert dispatched_jobs.count(1) == 1, (
        f"Job 1 was dispatched {dispatched_jobs.count(1)} times — duplicate dispatch detected"
    )
