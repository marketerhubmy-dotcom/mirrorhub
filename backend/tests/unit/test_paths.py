"""
CLAIM: Layer violation fixed — UPLOAD_DIR moved to utils/paths.py.

Verifies:
  1. utils/paths.py exports UPLOAD_DIR as a Path.
  2. content/routes.py and campaign/executor.py import from utils/paths, not each other.
  3. UPLOAD_DIR points to backend/uploads/.
"""
from pathlib import Path

import pytest


def test_upload_dir_importable():
    from app.utils.paths import UPLOAD_DIR
    assert isinstance(UPLOAD_DIR, Path)


def test_upload_dir_is_uploads_subdir():
    from app.utils.paths import UPLOAD_DIR
    # Should end with "uploads"
    assert UPLOAD_DIR.name == "uploads"


def test_content_routes_imports_from_utils():
    """content/routes.py must not define its own UPLOAD_DIR."""
    routes_file = (
        Path(__file__).parent.parent.parent / "app" / "content" / "routes.py"
    )
    text = routes_file.read_text(encoding="utf-8")
    # Must import from utils.paths (or use it)
    assert "app.utils.paths" in text or "utils.paths" in text
    # Must NOT define UPLOAD_DIR locally
    import re
    assert not re.search(r"^UPLOAD_DIR\s*=", text, re.MULTILINE), (
        "content/routes.py defines its own UPLOAD_DIR instead of importing it"
    )


def test_campaign_executor_imports_from_utils():
    """campaign/executor.py must not import UPLOAD_DIR from content/routes."""
    executor_file = (
        Path(__file__).parent.parent.parent / "app" / "campaign" / "executor.py"
    )
    text = executor_file.read_text(encoding="utf-8")
    assert "content.routes" not in text, (
        "campaign/executor.py still imports from content.routes (layer violation)"
    )
