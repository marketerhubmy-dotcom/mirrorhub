"""
CLAIM: Screenshot retention never exceeds the configured per-device limit.

Verifies:
  1. Cleanup removes oldest files when count exceeds the limit.
  2. Exactly settings.vision_max_screenshots files remain after cleanup.
  3. The most recent N files are kept (sorted by filename, which embeds timestamp).
  4. Null/empty scenarios (no files, exactly at limit) are handled safely.
  5. Cleanup is idempotent — running twice produces the same result.
"""
import re
from pathlib import Path

import pytest

from app.core.config import settings
from app.vision.screenshot import _cleanup_old_screenshots, SCREENSHOT_DIR


@pytest.fixture
def tmp_screenshot_dir(tmp_path, monkeypatch):
    """Redirect SCREENSHOT_DIR to a temp directory for the duration of the test."""
    monkeypatch.setattr(
        "app.vision.screenshot.SCREENSHOT_DIR", tmp_path
    )
    return tmp_path


def _make_screenshots(directory: Path, safe_id: str, count: int) -> list[Path]:
    """Create *count* fake PNG files named with an ascending timestamp suffix."""
    files = []
    for i in range(count):
        ts = f"20240101_00{i:04d}_00"
        f = directory / f"{safe_id}_{ts}.png"
        f.write_bytes(b"\x89PNG")          # minimal PNG magic bytes
        files.append(f)
    return files


# ── Core behaviour ────────────────────────────────────────────────────────────

def test_cleanup_removes_oldest_when_over_limit(tmp_screenshot_dir):
    limit = settings.vision_max_screenshots
    safe_id = "device_abc"
    all_files = _make_screenshots(tmp_screenshot_dir, safe_id, limit + 5)

    _cleanup_old_screenshots(safe_id)

    remaining = sorted(tmp_screenshot_dir.glob(f"{safe_id}_*.png"))
    assert len(remaining) == limit, (
        f"Expected {limit} files after cleanup, got {len(remaining)}"
    )


def test_cleanup_keeps_newest_files(tmp_screenshot_dir):
    limit = settings.vision_max_screenshots
    safe_id = "device_newest"
    all_files = _make_screenshots(tmp_screenshot_dir, safe_id, limit + 3)

    _cleanup_old_screenshots(safe_id)

    remaining = sorted(tmp_screenshot_dir.glob(f"{safe_id}_*.png"))
    # The newest files have the highest sort order
    expected_kept = sorted(all_files)[-(limit):]
    assert [f.name for f in remaining] == [f.name for f in expected_kept]


def test_cleanup_does_nothing_when_at_limit(tmp_screenshot_dir):
    limit = settings.vision_max_screenshots
    safe_id = "device_exact"
    all_files = _make_screenshots(tmp_screenshot_dir, safe_id, limit)

    _cleanup_old_screenshots(safe_id)

    remaining = list(tmp_screenshot_dir.glob(f"{safe_id}_*.png"))
    assert len(remaining) == limit


def test_cleanup_does_nothing_when_below_limit(tmp_screenshot_dir):
    limit = settings.vision_max_screenshots
    safe_id = "device_few"
    count = max(1, limit - 3)
    _make_screenshots(tmp_screenshot_dir, safe_id, count)

    _cleanup_old_screenshots(safe_id)

    remaining = list(tmp_screenshot_dir.glob(f"{safe_id}_*.png"))
    assert len(remaining) == count


def test_cleanup_does_nothing_when_no_files(tmp_screenshot_dir):
    """Empty directory must not raise."""
    _cleanup_old_screenshots("nonexistent_device")  # no files
    assert list(tmp_screenshot_dir.iterdir()) == []


def test_cleanup_is_idempotent(tmp_screenshot_dir):
    limit = settings.vision_max_screenshots
    safe_id = "device_idem"
    _make_screenshots(tmp_screenshot_dir, safe_id, limit + 10)

    _cleanup_old_screenshots(safe_id)
    count_first = len(list(tmp_screenshot_dir.glob(f"{safe_id}_*.png")))

    _cleanup_old_screenshots(safe_id)
    count_second = len(list(tmp_screenshot_dir.glob(f"{safe_id}_*.png")))

    assert count_first == count_second == limit


def test_cleanup_isolates_by_device(tmp_screenshot_dir):
    """Files from device_B should not be deleted when cleaning up device_A."""
    safe_id_a = "device_aaa"
    safe_id_b = "device_bbb"
    limit = settings.vision_max_screenshots

    _make_screenshots(tmp_screenshot_dir, safe_id_a, limit + 2)
    b_files = _make_screenshots(tmp_screenshot_dir, safe_id_b, 3)

    _cleanup_old_screenshots(safe_id_a)

    b_remaining = list(tmp_screenshot_dir.glob(f"{safe_id_b}_*.png"))
    assert len(b_remaining) == 3, "device_B files must be untouched"
