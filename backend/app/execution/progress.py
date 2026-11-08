import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.utils.adb_path import ADB
from app.websocket.manager import manager
from .state_machine import ExecutionState

# Screenshots land inside the existing uploads/ mount so they're web-accessible
from app.utils.paths import UPLOAD_DIR

SCREENSHOT_DIR = UPLOAD_DIR / "screenshots"


async def broadcast_state(state: ExecutionState) -> None:
    data = json.dumps({"type": "execution_state", "payload": state.to_dict()})
    await manager.broadcast_execution(state.device_id, data)


async def capture_screenshot(adb_address: str, job_id: int, step_label: str) -> str | None:
    """Capture a device screenshot, save to uploads/screenshots/, return web path."""
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() else "_" for c in step_label)[:30]
        filename = f"{job_id}_{ts}_{safe}.png"
        local_path = SCREENSHOT_DIR / filename

        proc = await asyncio.create_subprocess_exec(
            str(ADB), "-s", adb_address,
            "exec-out", "screencap", "-p",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        data, _ = await proc.communicate()
        if data:
            local_path.write_bytes(data)
            return f"/uploads/screenshots/{filename}"
    except Exception:
        pass
    return None
