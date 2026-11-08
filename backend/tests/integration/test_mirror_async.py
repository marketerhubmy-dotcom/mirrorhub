"""
CLAIM: The optional external scrcpy window service never blocks the event loop.

Rewritten (was targeting removed helpers `_launch_scrcpy`, `_processes`).
Verifies against the current `app.services.scrcpy` API:
  1. start_mirror offloads `adb connect` to a worker thread (asyncio.to_thread).
  2. A concurrent task completes while start_mirror is waiting.
  3. A failed `adb connect` is reported without spawning scrcpy.
  4. stop_mirror terminates a live process and forgets it.
  5. is_mirroring / active_mirrors reflect process liveness.
"""
import asyncio
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import scrcpy

_REAL_SLEEP = asyncio.sleep


async def _fast_sleep(_s):
    await _REAL_SLEEP(0)


@pytest.fixture(autouse=True)
def _clean_registry():
    scrcpy._active.clear()
    yield
    scrcpy._active.clear()


def _run_result(out: str):
    return SimpleNamespace(stdout=out, stderr="", returncode=0)


def _live_proc(pid=4242):
    p = MagicMock()
    p.pid = pid
    p.poll.return_value = None
    return p


@pytest.mark.asyncio
async def test_start_mirror_uses_to_thread_for_adb_connect():
    seen = []

    async def spy(func, *a, **kw):
        seen.append(func)
        return _run_result("connected to 1.2.3.4:5555")

    with patch.object(asyncio, "to_thread", spy), \
         patch.object(scrcpy.subprocess, "Popen", return_value=_live_proc()), \
         patch.object(scrcpy.asyncio, "sleep", _fast_sleep):
        ok, msg = await scrcpy.start_mirror("d1", "1.2.3.4:5555", "Phone")

    assert ok and "pid=4242" in msg
    assert seen and seen[0] is subprocess.run
    assert scrcpy.is_mirroring("d1")


@pytest.mark.asyncio
async def test_event_loop_stays_responsive_during_start():
    done = asyncio.Event()

    async def side():
        await _REAL_SLEEP(0.01)
        done.set()

    async def slow_to_thread(func, *a, **kw):
        await _REAL_SLEEP(0.2)  # simulate a slow `adb connect`
        return _run_result("connected to x")

    with patch.object(asyncio, "to_thread", slow_to_thread),          patch.object(scrcpy.subprocess, "Popen", return_value=_live_proc()),          patch.object(scrcpy.asyncio, "sleep", _fast_sleep):
        task = asyncio.create_task(scrcpy.start_mirror("d2", "1.2.3.4:5555"))
        t = asyncio.create_task(side())
        await asyncio.wait_for(done.wait(), timeout=1.0)
        assert not task.done(), "start_mirror finished before the slow connect (test is not exercising overlap)"
        ok, _ = await task
        await t
    assert ok is True


@pytest.mark.asyncio
async def test_failed_adb_connect_does_not_spawn_scrcpy():
    async def fake(func, *a, **kw):
        return _run_result("failed to connect to 1.2.3.4:5555")

    with patch.object(asyncio, "to_thread", fake), \
         patch.object(scrcpy.subprocess, "Popen") as popen:
        ok, msg = await scrcpy.start_mirror("d3", "1.2.3.4:5555")

    assert ok is False
    assert "ADB tidak dapat connect" in msg
    popen.assert_not_called()


@pytest.mark.asyncio
async def test_connect_timeout_is_reported():
    async def fake(func, *a, **kw):
        raise subprocess.TimeoutExpired(cmd="adb", timeout=10)

    with patch.object(asyncio, "to_thread", fake), \
         patch.object(scrcpy.subprocess, "Popen") as popen:
        ok, _ = await scrcpy.start_mirror("d4", "1.2.3.4:5555")
    assert ok is False
    popen.assert_not_called()


@pytest.mark.asyncio
async def test_already_running_is_idempotent():
    scrcpy._active["d5"] = _live_proc()
    with patch.object(scrcpy.subprocess, "Popen") as popen:
        ok, msg = await scrcpy.start_mirror("d5", "1.2.3.4:5555")
    assert (ok, msg) == (True, "Already running")
    popen.assert_not_called()


@pytest.mark.asyncio
async def test_immediate_crash_is_detected():
    async def fake(func, *a, **kw):
        return _run_result("connected to x")

    dead = MagicMock()
    dead.poll.return_value = 1
    with patch.object(asyncio, "to_thread", fake), \
         patch.object(scrcpy.subprocess, "Popen", return_value=dead), \
         patch.object(scrcpy.asyncio, "sleep", _fast_sleep):
        ok, msg = await scrcpy.start_mirror("d6", "1.2.3.4:5555")
    assert ok is False and "keluar awal" in msg
    assert not scrcpy.is_mirroring("d6")


@pytest.mark.asyncio
async def test_stop_mirror_terminates_and_forgets_process():
    p = _live_proc()
    scrcpy._active["d7"] = p
    assert await scrcpy.stop_mirror("d7") is True
    p.terminate.assert_called_once()
    assert "d7" not in scrcpy._active
    assert await scrcpy.stop_mirror("d7") is False


def test_active_mirrors_reports_only_live_processes():
    live, dead = _live_proc(), MagicMock()
    dead.poll.return_value = 0
    scrcpy._active.update({"live": live, "dead": dead})
    assert scrcpy.active_mirrors() == ["live"]
    assert scrcpy.is_mirroring("dead") is False
