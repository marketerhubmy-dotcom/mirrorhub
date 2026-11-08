"""
Shared filesystem path constants.

Import from here instead of computing paths inline in individual modules.
This keeps path logic in one place and makes the project layout relocatable.

Usage:
    from app.utils.paths import UPLOAD_DIR
"""
from pathlib import Path

# backend/ directory (contains uploads/, logs/, mirrorhub.db)
from app.core import runtime_paths

UPLOAD_DIR: Path = runtime_paths.uploads_dir()
