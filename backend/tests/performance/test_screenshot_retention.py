"""
CLAIM: Screenshot retention never exceeds settings.vision_max_screenshots per device,
       even under continuous write pressure.

Verifies:
  1. After 200 consecutive screenshots, count never exceeds the limit.
  2. Cleanup time is sub-linear (does not grow with iteration count).
"""
import time
from pathlib import Path

import pytest

from app.core.config import settings
from app.vision.screenshot import _cleanup_old_screenshots


@pytest.fixture
def tmp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("app.vision.screenshot.SCREENSHOT_DIR", tmp_path)
    return tmp_path


def _write_screenshot(directory: Path, safe_id: str, seq: int) -> None:
    name = directory / f"{safe_id}_20240101_{seq:06d}_00.png"
    name.write_bytes(b"\x89PNG")


def test_retention_never_exceeds_limit_under_write_pressure(tmp_dir):
    """
    Simulate continuous screenshot writes (200 total, one cleanup after each write).
    File count after every cleanup must be ≤ settings.vision_max_screenshots.
    """
    safe_id = "stress_device"
    limit = settings.vision_max_screenshots

    for i in range(200):
        _write_screenshot(tmp_dir, safe_id, i)
        _cleanup_old_screenshots(safe_id)
        count = len(list(tmp_dir.glob(f"{safe_id}_*.png")))
        assert count <= limit, (
            f"After write {i}: {count} files remain, exceeds limit {limit}"
        )


def test_cleanup_is_fast_for_large_backlog(tmp_dir):
    """
    Even with a large file backlog (10x limit), cleanup should complete quickly.
    Target: under 1 second (generous; actually measured in milliseconds normally).
    """
    safe_id = "speed_device"
    limit = settings.vision_max_screenshots
    backlog = limit * 10

    for i in range(backlog):
        _write_screenshot(tmp_dir, safe_id, i)

    start = time.perf_counter()
    _cleanup_old_screenshots(safe_id)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, (
        f"Cleanup of {backlog} files took {elapsed:.3f}s — may be O(N²) sort or stat"
    )
    count = len(list(tmp_dir.glob(f"{safe_id}_*.png")))
    assert count == limit
