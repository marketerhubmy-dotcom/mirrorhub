import asyncio
import io
import subprocess
from pathlib import Path

from app.utils.adb_path import ADB
from typing import Callable, Awaitable

from PIL import Image

_streaming: dict[str, asyncio.Task] = {}
_capture_events: dict[str, asyncio.Event] = {}


async def _capture_frame(adb: Path, adb_address: str) -> bytes | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            str(adb), "-s", adb_address, "exec-out", "screencap", "-p",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=6.0)

        if not stdout or len(stdout) < 1000:
            return None

        img = Image.open(io.BytesIO(stdout))
        img.thumbnail((480, 1040), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=65, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


async def _loop(
    device_id: str,
    adb_address: str,
    broadcast: Callable[[str, bytes], Awaitable[None]],
) -> None:
    adb = ADB
    event = asyncio.Event()
    _capture_events[device_id] = event

    while True:
        frame = await _capture_frame(adb, adb_address)
        if frame:
            await broadcast(device_id, frame)

        # Wait for next interval OR immediate capture request from control
        try:
            await asyncio.wait_for(event.wait(), timeout=0.2)
            event.clear()
        except asyncio.TimeoutError:
            pass


def start(
    device_id: str,
    adb_address: str,
    broadcast: Callable[[str, bytes], Awaitable[None]],
) -> None:
    task = _streaming.get(device_id)
    if task and not task.done():
        return
    loop = asyncio.get_event_loop()
    _streaming[device_id] = loop.create_task(
        _loop(device_id, adb_address, broadcast)
    )


def stop(device_id: str) -> None:
    task = _streaming.pop(device_id, None)
    if task:
        task.cancel()


def request_capture(device_id: str) -> None:
    """Trigger an immediate screencap — call this after any control input."""
    event = _capture_events.get(device_id)
    if event:
        event.set()


def active() -> list[str]:
    return [did for did, t in _streaming.items() if not t.done()]
