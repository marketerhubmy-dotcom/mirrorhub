"""
Converts a ContentJob into AutomationRunner-compatible step dicts.
Does NOT import or call AutomationRunner — returns steps only.
Platform-agnostic design: add new platforms by adding a new _*_steps() function.
"""
from app.content.models import ContentJob


def build_content_workflow(
    job: ContentJob,
    image_local_path: str,
    platform: str = "ytcreate",
    post_type: str = "draft",
    schedule_time: str | None = None,
) -> list[dict]:
    """
    Convert a ContentJob to automation steps for any supported platform.

    platform: ytcreate | tiktok | capcut | instagram
    post_type: post_now | draft | schedule
    Returns list of step dicts compatible with AutomationRunner.execute().
    """
    script = _compose_script(job)
    device_img = "/sdcard/DCIM/mirrorhub/product.jpg"

    steps: list[dict] = [
        {
            "type": "push_file",
            "local": image_local_path,
            "remote": device_img,
            "label": "Upload gambar ke phone",
        },
        {"type": "wait", "seconds": 1},
    ]

    platform_builders = {
        "ytcreate": _ytcreate_steps,
        "tiktok": _ytcreate_steps,   # future: replace with direct TikTok steps
        "capcut": _ytcreate_steps,   # future: replace with CapCut steps
        "instagram": _ytcreate_steps, # future: replace with Instagram steps
    }
    builder = platform_builders.get(platform, _ytcreate_steps)
    steps += builder(script, post_type, schedule_time)
    return steps


def _compose_script(job: ContentJob) -> str:
    """Build the prompt text to send to the video platform."""
    if job.video_prompt:
        return job.video_prompt
    parts = [p for p in [job.hook, job.story, job.cta] if p]
    return "\n".join(parts)


def _ytcreate_steps(
    script: str, post_type: str, schedule_time: str | None
) -> list[dict]:
    return [
        {
            "type": "open_app",
            "package": "com.google.android.apps.youtube.creator",
            "label": "Buka YT Create",
        },
        {"type": "wait", "seconds": 4, "label": "Tunggu YT Create load"},
        {
            "type": "tap_text",
            "text": "New project",
            "fallback": [0.5, 0.91],
            "label": "Tap New project",
        },
        {"type": "wait", "seconds": 2},
        {
            "type": "tap_text",
            "text": "Script",
            "fallback": [0.25, 0.45],
            "label": "Pilih Script mode",
        },
        {"type": "wait", "seconds": 1},
        {"type": "tap_rel", "x": 0.5, "y": 0.45, "label": "Tap script input"},
        {"type": "wait", "seconds": 0.5},
        {"type": "type_text", "text": script, "label": "Input video prompt"},
        {"type": "wait", "seconds": 1},
        {
            "type": "tap_text",
            "text": "Media",
            "fallback": [0.15, 0.85],
            "label": "Tap Media",
        },
        {"type": "wait", "seconds": 1},
        {
            "type": "tap_text",
            "text": "Gallery",
            "fallback": [0.25, 0.45],
            "label": "Pilih Gallery",
        },
        {"type": "wait", "seconds": 2},
        {"type": "tap_rel", "x": 0.15, "y": 0.25, "label": "Pilih gambar produk"},
        {"type": "wait", "seconds": 0.5},
        {
            "type": "tap_text",
            "text": "Add",
            "fallback": [0.85, 0.92],
            "label": "Add gambar",
        },
        {"type": "wait", "seconds": 1},
        {
            "type": "tap_text",
            "text": "Generate",
            "fallback": [0.5, 0.87],
            "label": "Generate video",
        },
        {"type": "wait", "seconds": 5},
        {"type": "wait", "seconds": 90, "label": "Tunggu video siap (90s)"},
        {
            "type": "tap_text",
            "text": "Continue",
            "fallback": [0.85, 0.12],
            "label": "Continue",
        },
        {"type": "wait", "seconds": 2},
        {
            "type": "tap_text",
            "text": "Share",
            "fallback": [0.85, 0.12],
            "label": "Tap Share",
        },
        {"type": "wait", "seconds": 2},
        {
            "type": "tap_text",
            "text": "TikTok",
            "fallback": [0.5, 0.55],
            "label": "Pilih TikTok",
        },
        {"type": "wait", "seconds": 5},
        {
            "type": "tap_text",
            "text": "Next",
            "fallback": [0.85, 0.07],
            "label": "Next",
        },
        {"type": "wait", "seconds": 3},
        *_post_type_steps(post_type, schedule_time),
    ]


def _post_type_steps(post_type: str, schedule_time: str | None) -> list[dict]:
    if post_type == "post_now":
        return [
            {
                "type": "tap_text",
                "text": "Post",
                "fallback": [0.85, 0.92],
                "label": "Post sekarang ✅",
            }
        ]
    if post_type == "draft":
        return [
            {
                "type": "tap_text",
                "text": "Drafts",
                "fallback": [0.15, 0.92],
                "label": "Simpan Draft ✅",
            }
        ]
    if post_type == "schedule" and schedule_time:
        return [
            {
                "type": "tap_text",
                "text": "Schedule",
                "fallback": [0.5, 0.78],
                "label": "Tap Schedule",
            },
            {"type": "wait", "seconds": 1},
            {
                "type": "tap_text",
                "text": "Confirm",
                "fallback": [0.85, 0.92],
                "label": "Confirm schedule ✅",
            },
        ]
    return []
