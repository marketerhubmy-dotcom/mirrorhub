import asyncio
import subprocess
from pathlib import Path
from typing import Callable, Awaitable

_procs: dict[str, asyncio.subprocess.Process] = {}
_tasks: dict[str, asyncio.Task] = {}
_viewers: dict[str, list[Callable[[bytes], Awaitable[None]]]] = {}


def _adb() -> Path:
    base = Path(__file__).parent.parent.parent.parent
    return base / "tools" / "scrcpy" / "scrcpy-win64-v4.0" / "adb.exe"


async def _reader(device_id: str) -> None:
    proc = _procs.get(device_id)
    if not proc:
        return
    try:
        while True:
            chunk = await proc.stdout.read(16384)
            if not chunk:
                break
            for cb in list(_viewers.get(device_id, [])):
                try:
                    await cb(chunk)
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        _procs.pop(device_id, None)
        _tasks.pop(device_id, None)


async def add_viewer(
    device_id: str,
    adb_address: str,
    on_chunk: Callable[[bytes], Awaitable[None]],
) -> None:
    if device_id not in _viewers:
        _viewers[device_id] = []
    _viewers[device_id].append(on_chunk)

    proc = _procs.get(device_id)
    if proc is None or proc.returncode is not None:
        proc = await asyncio.create_subprocess_exec(
            str(_adb()), "-s", adb_address,
            "exec-out", "screenrecord",
            "--output-format=h264",
            "--bit-rate=3000000",
            "--size=540x1200",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        _procs[device_id] = proc
        _tasks[device_id] = asyncio.get_event_loop().create_task(_reader(device_id))


def remove_viewer(
    device_id: str,
    on_chunk: Callable[[bytes], Awaitable[None]],
) -> None:
    viewers = _viewers.get(device_id, [])
    if on_chunk in viewers:
        viewers.remove(on_chunk)
    if not viewers:
        _viewers.pop(device_id, None)
        proc = _procs.pop(device_id, None)
        if proc:
            proc.terminate()
        task = _tasks.pop(device_id, None)
        if task:
            task.cancel()
