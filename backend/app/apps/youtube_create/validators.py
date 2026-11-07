"""
Input validation for the YouTube Create plugin.

Called before any device interaction.  Returns PluginResult so the caller
never needs to handle raw exceptions for expected bad-input cases.
"""
from pathlib import Path

from app.apps.base import PluginResult
from .constants import MAX_IMAGES
from .state import ERRORS


def validate(job: dict) -> PluginResult:
    """
    Validate a job dict.  Returns PluginResult(success=True) if everything
    looks good, or PluginResult(success=False, ...) with the first error found.
    """
    prompt = job.get("video_prompt", "").strip()
    if not prompt:
        return PluginResult(
            success=False,
            code=ERRORS["INVALID_JOB"].code,
            reason="video_prompt is required and must not be empty",
            suggested_retry=False,
        )

    images = _resolve_images(job)

    if len(images) > MAX_IMAGES:
        err = ERRORS["TOO_MANY_IMAGES"]
        return PluginResult(
            success=False,
            code=err.code,
            reason=err.reason,
            suggested_retry=err.suggested_retry,
        )

    missing = [p for p in images if not Path(p).exists()]
    if missing:
        return PluginResult(
            success=False,
            code=ERRORS["MISSING_IMAGE"].code,
            reason=f"Image not found: {missing[0]}",
            suggested_retry=False,
        )

    return PluginResult(success=True, code="OK", reason="Valid")


def _resolve_images(job: dict) -> list[str]:
    """Extract the canonical image list from job, supporting both list and single forms."""
    images = job.get("image_paths", [])
    if isinstance(images, str):
        images = [images]
    if not images:
        single = job.get("image_path", "")
        if single:
            images = [single]
    return [str(p) for p in images if p]
