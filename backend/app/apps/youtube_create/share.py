"""
Share phase helpers for the YouTube Create plugin.
Generates the share + post steps; does not execute ADB directly.
"""


def build_share_steps(
    device_id: str = "",
    target_app: str = "TikTok",
    post_type: str = "draft",
    schedule_time: str | None = None,
) -> list[dict]:
    """Return the share-to-TikTok and post steps."""
    _d = {"device_id": device_id}
    return [
        {
            "type": "ytcreate_share",
            "target_app": target_app,
            "label": f"Share ke {target_app}",
            "retry_max": 2,
            **_d,
        },
        {
            "type": "ytcreate_post",
            "post_type": post_type,
            "schedule_time": schedule_time,
            "label": f"Post ({post_type})",
            "retry_max": 2,
            **_d,
        },
    ]
