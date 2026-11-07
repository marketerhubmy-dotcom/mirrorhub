"""
Campaign Executor — bridges a CampaignJob to the correct AppPlugin.

This is the ONLY place that knows about both the Campaign module and the
plugin layer.  The Dispatcher calls dispatch() and gets back a PluginResult.

Platform routing:
    "youtube_create" → YouTubeCreatePlugin
    "tiktok"         → TikTokPlugin
    Others are rejected with INVALID_JOB.

Job dict assembly:
    Loaded from ContentJob fields + CampaignJob.job_config (overrides).
    The user can put any extra plugin fields in job_config_json
    (e.g. video_path for TikTok, post_type, hashtags).
"""
import json

from app.apps.base import PluginResult
from app.models.database import AsyncSessionLocal
from app.campaign.models import CampaignJob
from app.models.device import Device


async def dispatch(cj: CampaignJob, device: Device) -> PluginResult:
    """
    Build the job dict from ContentJob + job_config, then call the plugin.

    Args:
        cj:     CampaignJob row (has platform, content_job_id, job_config_json)
        device: Device row (has adb_address, device_id)
    """
    job = await _build_job_dict(cj)
    adb_address = device.adb_address or ""
    device_id = device.device_id

    if cj.platform == "youtube_create":
        from app.apps.youtube_create.plugin import YouTubeCreatePlugin
        return await YouTubeCreatePlugin().execute(job, adb_address, device_id)

    if cj.platform == "tiktok":
        from app.apps.tiktok.plugin import TikTokPlugin
        return await TikTokPlugin().execute(job, adb_address, device_id)

    return PluginResult(
        success=False,
        code="INVALID_PLATFORM",
        reason=f"Unsupported platform: {cj.platform}",
        suggested_retry=False,
    )


async def simulate(cj: CampaignJob) -> PluginResult:
    """Dry-run: build job dict and call plugin with simulate=True."""
    job = await _build_job_dict(cj)
    job["simulate"] = True

    if cj.platform == "youtube_create":
        from app.apps.youtube_create.plugin import YouTubeCreatePlugin
        return await YouTubeCreatePlugin().execute(job, adb_address="", device_id="")

    if cj.platform == "tiktok":
        from app.apps.tiktok.plugin import TikTokPlugin
        return await TikTokPlugin().execute(job, adb_address="", device_id="")

    return PluginResult(
        success=False,
        code="INVALID_PLATFORM",
        reason=f"Unsupported platform: {cj.platform}",
    )


# ── Job dict assembly ─────────────────────────────────────────────────────────

async def _build_job_dict(cj: CampaignJob) -> dict:
    """
    Assemble the job dict the plugin expects.

    Base fields come from ContentJob (if content_job_id is set).
    job_config_json fields are merged on top and take precedence.
    """
    base: dict = {
        "content_job_id": cj.content_job_id,
    }

    # Load ContentJob fields if linked
    if cj.content_job_id:
        async with AsyncSessionLocal() as db:
            from app.content.models import ContentJob
            content = await db.get(ContentJob, cj.content_job_id)
            if content:
                base.update(_content_job_to_dict(content, cj.platform))

    # Merge job_config on top (these are user-defined overrides)
    override = json.loads(cj.job_config_json or "{}")
    base.update(override)

    return base


def _content_job_to_dict(content, platform: str) -> dict:
    """Extract the fields each platform's plugin needs from a ContentJob."""
    import json as _json
    hashtags = _json.loads(content.hashtags or "[]")
    images = _json.loads(content.reference_images or "[]")

    if platform == "youtube_create":
        from app.utils.paths import UPLOAD_DIR
        image_paths = [str(UPLOAD_DIR / img) for img in images]
        return {
            "video_prompt": content.video_prompt or content.hook or content.story or "",
            "image_paths": image_paths,
            "image_path": image_paths[0] if image_paths else "",
        }

    if platform == "tiktok":
        return {
            "caption": content.caption or "",
            "hashtags": hashtags,
        }

    return {}
