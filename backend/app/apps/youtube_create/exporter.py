"""
Export phase helpers for the YouTube Create plugin.

These functions generate export-related steps; they do not execute ADB commands
directly.  The actual tapping is handled by step handlers in execution/.
"""
from .constants import EXPORT_TIMEOUT, PREFERRED_RESOLUTION


def build_export_steps(
    device_id: str = "",
    resolution: str = PREFERRED_RESOLUTION,
) -> list[dict]:
    """
    Return the export step(s) for the given resolution preference.
    If a resolution selector is needed, it is prepended before the main export tap.
    """
    _d = {"device_id": device_id}
    steps: list[dict] = []

    if resolution == "1080p":
        steps.append({
            "type": "ytcreate_select_resolution",
            "resolution": resolution,
            "label": f"Pilih resolusi {resolution}",
            "retry_max": 1,
            **_d,
        })

    steps.append({
        "type": "ytcreate_export",
        "export_timeout": EXPORT_TIMEOUT,
        "label": "Export video",
        "retry_max": 2,
        **_d,
    })

    return steps
