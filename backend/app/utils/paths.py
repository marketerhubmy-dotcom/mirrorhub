"""
Shared filesystem path constants.

Import from here instead of computing paths inline in individual modules.
This keeps path logic in one place and makes the project layout relocatable.

Usage:
    from app.utils.paths import UPLOAD_DIR
"""
from pathlib import Path

# backend/ directory (contains uploads/, logs/, mirrorhub.db)
_BACKEND_ROOT = Path(__file__).parent.parent.parent

UPLOAD_DIR: Path = _BACKEND_ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
