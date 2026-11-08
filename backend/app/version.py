"""
MirrorHub version constants.

Single source of truth for the application version.
Imported by the /api/v1/system/about endpoint and the About page.
"""
import sys
import platform
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.1.0"
VERSION_TUPLE = (1, 1, 0)
RELEASE_NAME = "Performance"
BUILD_DATE = "2026-11-09"

# Plugins and modules that ship as part of this release
PLUGIN_VERSIONS: dict[str, str] = {
    "youtube_create": "1.0.0",
    "tiktok": "1.0.0",
}

MODULE_VERSIONS: dict[str, str] = {
    "execution_engine": "1.0.0",
    "vision_engine": "1.0.0",
    "workflow_engine": "1.0.0",
    "campaign_scheduler": "1.0.0",
    "content_pipeline": "1.0.0",
}


def get_build_info() -> dict:
    """Return a dict suitable for the /about API response."""
    from app.core.runtime_paths import db_path as _db_path
    db_path = _db_path()
    return {
        "version": VERSION,
        "release_name": RELEASE_NAME,
        "build_date": BUILD_DATE,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "plugins": PLUGIN_VERSIONS,
        "modules": MODULE_VERSIONS,
        "database": {
            "path": str(db_path),
            "exists": db_path.exists(),
            "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        },
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
