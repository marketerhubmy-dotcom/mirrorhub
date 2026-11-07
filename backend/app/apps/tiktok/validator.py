"""
Input validation for the TikTok Publisher plugin.

Called before any device interaction.  Returns PluginResult so callers
never need to handle raw exceptions for expected bad-input cases.
"""
from pathlib import Path

from app.apps.base import PluginResult
from .constants import ALLOWED_EXTENSIONS, MAX_CAPTION_LENGTH
from .state import ERRORS


def validate(job: dict) -> PluginResult:
    """
    Validate a TikTok publish job dict.

    Accepted job keys (all optional except video_path):
        video_path    str  — local path to the exported video file
        caption       str  — post caption (may contain {{variables}})
        hashtags      list — list of hashtag strings (without #)
        product_id    str  — TikTok Shop product ID to attach
        first_comment str  — optional first comment to post after publishing
    """
    video_path = job.get("video_path", "").strip()
    if not video_path:
        return PluginResult(
            success=False,
            code=ERRORS["INVALID_JOB"].code,
            reason="video_path is required and must not be empty",
            suggested_retry=False,
        )

    p = Path(video_path)
    if not p.exists():
        return PluginResult(
            success=False,
            code=ERRORS["VIDEO_MISSING"].code,
            reason=f"Video file not found: {video_path}",
            suggested_retry=False,
        )

    if p.suffix.lower() not in ALLOWED_EXTENSIONS:
        return PluginResult(
            success=False,
            code=ERRORS["VIDEO_WRONG_FORMAT"].code,
            reason=f"Unsupported format '{p.suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
            suggested_retry=False,
        )

    caption = job.get("caption", "")
    hashtags = job.get("hashtags", [])
    if isinstance(hashtags, str):
        hashtags = [hashtags]

    # Build the final caption to check length
    from .caption import build_caption
    full_caption = build_caption(caption, hashtags)
    if len(full_caption) > MAX_CAPTION_LENGTH:
        return PluginResult(
            success=False,
            code=ERRORS["INVALID_JOB"].code,
            reason=f"Caption exceeds {MAX_CAPTION_LENGTH} characters ({len(full_caption)} chars)",
            suggested_retry=False,
        )

    return PluginResult(success=True, code="OK", reason="Valid")


def validate_product_job(job: dict) -> PluginResult:
    """Validate product attachment fields independently."""
    product_id = job.get("product_id", "").strip()
    if not product_id:
        return PluginResult(success=True, code="OK", reason="No product — skipping attachment")

    from .product import product_manager
    product = product_manager.get(product_id)
    if not product:
        return PluginResult(
            success=False,
            code=ERRORS["PRODUCT_MISSING"].code,
            reason=f"Product '{product_id}' not found in product registry",
            suggested_retry=False,
        )

    return PluginResult(success=True, code="OK", reason="Product found")
