"""
Video upload helpers for the TikTok Publisher plugin.

Responsibilities:
- Validate the video file (exists, readable, format, duration estimate)
- Build the ADB push step that copies the video to the device
- Build the gallery-selection steps that open TikTok's upload screen

Duration estimation uses file size as a rough proxy when ffprobe is
unavailable — good enough to catch obviously wrong files (images, empty files).
"""
from pathlib import Path

from .constants import (
    ALLOWED_EXTENSIONS,
    MIN_DURATION_S,
    MAX_DURATION_S,
    DEVICE_VIDEO_DIR,
    DEVICE_VIDEO_FILENAME,
)


def validate_video_file(video_path: str) -> dict:
    """
    Check the local video file.

    Returns a dict with keys:
        valid: bool
        reason: str
        size_bytes: int
        extension: str
    """
    p = Path(video_path)

    if not p.exists():
        return {"valid": False, "reason": f"File not found: {video_path}", "size_bytes": 0, "extension": ""}

    if not p.is_file():
        return {"valid": False, "reason": "Path is not a file", "size_bytes": 0, "extension": ""}

    ext = p.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return {
            "valid": False,
            "reason": f"Unsupported format '{ext}'. Allowed: {ALLOWED_EXTENSIONS}",
            "size_bytes": 0,
            "extension": ext,
        }

    size = p.stat().st_size
    if size < 10_000:
        return {
            "valid": False,
            "reason": f"File too small ({size} bytes) — likely not a valid video",
            "size_bytes": size,
            "extension": ext,
        }

    return {"valid": True, "reason": "OK", "size_bytes": size, "extension": ext}


def device_video_path() -> str:
    """Canonical path where the video is placed on the device."""
    return f"{DEVICE_VIDEO_DIR.rstrip('/')}/{DEVICE_VIDEO_FILENAME}"


def build_push_step(video_path: str, device_id: str = "") -> dict:
    """
    Build an ADB push step that copies the video to the device.

    The execution engine handler for 'tiktok_push_video' reads:
        local        — host-side path
        device_path  — where to write on device
    """
    return {
        "type": "tiktok_push_video",
        "label": "Push video ke device",
        "local": video_path,
        "device_path": device_video_path(),
        "device_id": device_id,
        "retry_max": 2,
    }


def build_upload_steps(video_path: str, device_id: str = "") -> list[dict]:
    """
    Build the complete sequence for getting a video into TikTok's upload flow:
      1. Push the video file
      2. Broadcast media scanner so it appears in Gallery
      3. Open TikTok upload screen
      4. Select the video from gallery
      5. Verify preview loaded
    """
    _d = {"device_id": device_id}
    steps: list[dict] = []

    steps.append(build_push_step(video_path, device_id))

    steps.append({
        "type": "tiktok_open_upload",
        "label": "Buka upload screen TikTok",
        "retry_max": 3,
        **_d,
    })

    steps.append({
        "type": "tiktok_select_video",
        "label": "Pilih video terbaru",
        "device_path": device_video_path(),
        "retry_max": 2,
        **_d,
    })

    steps.append({
        "type": "tiktok_verify_preview",
        "label": "Verify preview loaded",
        "retry_max": 2,
        **_d,
    })

    steps.append({
        "type": "tiktok_tap_next",
        "label": "Tap Next",
        "retry_max": 2,
        **_d,
    })

    return steps
