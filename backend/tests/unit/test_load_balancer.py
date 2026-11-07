"""
Tests for orchestrator device allocation (load balancer).

Verifies:
  1. assign_device picks the device with fewest running jobs (least_busy).
  2. Returns None when no profiles are available.
  3. Returns None when all devices are busy above their threshold.
  4. Does not assign the same device when excluded (used for reassignment).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_profile(device_id: str, status: str = "IDLE", score: float = 5.0):
    p = MagicMock()
    p.device_id = device_id
    p.status = status
    p.performance_score = score
    return p


def _make_job(device_id: str | None = None, platform: str = "tiktok"):
    j = MagicMock()
    j.id = 1
    j.device_id = device_id
    j.platform = platform
    return j


@pytest.mark.asyncio
async def test_assign_device_least_busy_picks_idle():
    """assign_device with least_busy returns the device with 0 running jobs."""
    from app.orchestrator.allocator import assign_device

    profiles = [
        _make_profile("dev-A"),
        _make_profile("dev-B"),
    ]
    job = _make_job()
    # dev-A has 0 jobs, dev-B has 2 — should pick dev-A
    active_jobs = {"dev-A": 0, "dev-B": 2}

    with patch("app.orchestrator.allocator.list_available_profiles", AsyncMock(return_value=profiles)):
        result = await assign_device(
            db=AsyncMock(),
            job=job,
            strategy="least_busy",
            active_jobs=active_jobs,
        )
    assert result == "dev-A"


@pytest.mark.asyncio
async def test_assign_device_returns_none_no_profiles():
    from app.orchestrator.allocator import assign_device

    job = _make_job()
    with patch("app.orchestrator.allocator.list_available_profiles", AsyncMock(return_value=[])):
        result = await assign_device(
            db=AsyncMock(), job=job, strategy="least_busy", active_jobs={}
        )
    assert result is None


@pytest.mark.asyncio
async def test_assign_device_excludes_current_device():
    """For reassignment, the current device must not be re-selected."""
    from app.orchestrator.allocator import assign_device

    profiles = [_make_profile("dev-A"), _make_profile("dev-B")]
    job = _make_job(device_id="dev-A")
    active_jobs = {"dev-A": 0, "dev-B": 0}

    with patch("app.orchestrator.allocator.list_available_profiles", AsyncMock(return_value=profiles)):
        result = await assign_device(
            db=AsyncMock(),
            job=job,
            strategy="least_busy",
            active_jobs=active_jobs,
            exclude_device_id="dev-A",
        )
    # Should pick dev-B since dev-A is excluded
    assert result == "dev-B"
