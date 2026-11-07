"""
Centralized knowledge base for the Agent Layer.

Provides static facts about plugins, platforms, and campaign strategies.
Agents read from here instead of hard-coding platform rules.
"""
from __future__ import annotations

PLUGIN_CAPABILITIES: dict[str, dict] = {
    "tiktok": {
        "name": "TikTok Publisher",
        "steps": ["open_app", "navigate_create", "upload_video", "add_caption", "add_hashtags", "publish"],
        "requires": ["video_path", "caption"],
        "optional": ["hashtags", "first_comment", "schedule_time"],
        "avg_duration_s": 90,
        "failure_modes": ["video_upload_timeout", "login_required", "caption_too_long"],
    },
    "youtube_create": {
        "name": "YouTube Create",
        "steps": ["open_app", "new_project", "apply_prompt", "generate_video", "export"],
        "requires": ["video_prompt"],
        "optional": ["visual_style", "duration"],
        "avg_duration_s": 180,
        "failure_modes": ["generation_timeout", "quota_exceeded", "network_error"],
    },
}

PLATFORM_DEFAULTS: dict[str, dict] = {
    "tiktok": {
        "priority": 2,
        "retry_max": 3,
        "content_duration": "15s",
        "audience": "18-35 year old TikTok users",
    },
    "youtube_create": {
        "priority": 2,
        "retry_max": 2,
        "content_duration": "30s",
        "audience": "YouTube Shorts viewers",
    },
}

RECOVERY_STRATEGIES: list[str] = [
    "retry",        # increment retry_count and re-queue
    "reassign",     # move to a different device
    "pause",        # pause the campaign
    "abort",        # cancel this job permanently
]

DISTRIBUTION_STRATEGIES: list[str] = [
    "least_busy",
    "round_robin",
    "fastest",
    "priority_device",
]

OPTIMIZATION_AREAS: list[str] = [
    "device_selection",
    "retry_strategy",
    "scheduling_time",
    "plugin_choice",
    "workflow_template",
]


def get_plugin_info(plugin: str) -> dict:
    return PLUGIN_CAPABILITIES.get(plugin, {})


def get_platform_defaults(platform: str) -> dict:
    return PLATFORM_DEFAULTS.get(platform, PLATFORM_DEFAULTS["tiktok"])


def get_estimated_duration(plugin: str) -> float:
    """Return estimated job duration in seconds."""
    info = get_plugin_info(plugin)
    return float(info.get("avg_duration_s", 120))


def estimate_campaign_duration(count: int, plugin: str, device_count: int = 1) -> dict:
    """
    Rough estimate for a campaign of `count` jobs on `device_count` devices.

    Returns dict with total_s, per_device_s, formatted.
    """
    per_job = get_estimated_duration(plugin)
    total_s = count * per_job
    parallel_s = total_s / max(device_count, 1)
    hours, rem = divmod(int(parallel_s), 3600)
    mins = rem // 60
    return {
        "total_s": total_s,
        "parallel_s": parallel_s,
        "formatted": f"{hours}h {mins}m" if hours else f"{mins}m",
        "per_job_s": per_job,
        "device_count": device_count,
    }
