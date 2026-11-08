import asyncio
import struct
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.utils.adb_path import ADB

from app.utils.paths import UPLOAD_DIR

SCREENSHOT_DIR = UPLOAD_DIR / "vision"


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Read PNG width/height from header without PIL."""
    if len(data) >= 24 and data[:8] == b'\x89PNG\r\n\x1a\n':
        w = struct.unpack('>I', data[16:20])[0]
        h = struct.unpack('>I', data[20:24])[0]
        return (w, h)
    return (0, 0)


def _cleanup_old_screenshots(safe_id: str) -> None:
    """Keep only the latest settings.vision_max_screenshots files per device."""
    files = sorted(SCREENSHOT_DIR.glob(f"{safe_id}_*.png"))
    for old_file in files[:-settings.vision_max_screenshots]:
        try:
            old_file.unlink()
        except OSError:
            pass


@dataclass
class CaptureResult:
    data: bytes
    web_path: str | None
    width: int
    height: int
    timestamp: datetime
    device_id: str


async def capture(adb_address: str, device_id: str) -> CaptureResult:
    """Capture PNG screenshot, save to disk with rotation, return CaptureResult."""
    ts = datetime.now(timezone.utc)
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        safe_id = device_id.replace(":", "_").replace("-", "_")
        filename = f"{safe_id}_{ts.strftime('%Y%m%d_%H%M%S_%f')}.png"
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
            _cleanup_old_screenshots(safe_id)
            w, h = _png_dimensions(data)
            return CaptureResult(
                data=data,
                web_path=f"/uploads/vision/{filename}",
                width=w,
                height=h,
                timestamp=ts,
                device_id=device_id,
            )
    except Exception:
        pass
    return CaptureResult(data=b"", web_path=None, width=0, height=0, timestamp=ts, device_id=device_id)
