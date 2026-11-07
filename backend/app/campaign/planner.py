"""
Campaign Planner — helpers for analysis, estimation, and validation.

None of these functions mutate state; they only read and compute.
"""
from datetime import datetime, timedelta, timezone

from app.models.database import AsyncSessionLocal
from . import repository as repo
from .models import CampaignJob


# ── Time estimation ───────────────────────────────────────────────────────────

AVG_JOB_DURATION_S: float = 120.0   # fallback average if no history yet


async def estimate_remaining_time(campaign_id: int) -> dict:
    """
    Estimate how long until the campaign finishes.

    Returns:
        estimated_seconds  — total seconds remaining
        estimated_finish   — UTC ISO datetime string
        remaining_jobs     — count of non-terminal jobs
        avg_job_duration_s — average used for the estimate
    """
    async with AsyncSessionLocal() as db:
        jobs = await repo.list_campaign_jobs(db, campaign_id)
        stats = await repo.get_campaign_stats(db, campaign_id)

    remaining = [j for j in jobs if j.status not in ("COMPLETED", "CANCELLED", "FAILED")]
    avg = stats.get("avg_duration_s") or AVG_JOB_DURATION_S
    if avg < 10:
        avg = AVG_JOB_DURATION_S

    total_s = len(remaining) * avg
    finish = datetime.now(timezone.utc) + timedelta(seconds=total_s)

    return {
        "estimated_seconds": round(total_s, 0),
        "estimated_finish": finish.isoformat() + "Z",
        "remaining_jobs": len(remaining),
        "avg_job_duration_s": round(avg, 1),
    }


# ── Dependency graph ──────────────────────────────────────────────────────────

async def get_dependency_graph(campaign_id: int) -> dict[int, list[int]]:
    """
    Return a dict mapping job_id → list of job_ids it depends on.
    Only includes jobs with at least one dependency.
    """
    async with AsyncSessionLocal() as db:
        jobs = await repo.list_campaign_jobs(db, campaign_id)

    graph: dict[int, list[int]] = {}
    for j in jobs:
        if j.depends_on_job_id:
            graph[j.id] = [j.depends_on_job_id]
    return graph


def validate_dependencies(jobs: list[CampaignJob]) -> list[str]:
    """
    Check for circular dependencies in a list of CampaignJobs.
    Returns a list of error strings (empty if no issues).
    """
    id_set = {j.id for j in jobs}
    errors: list[str] = []

    # Build adjacency list
    edges: dict[int, int | None] = {j.id: j.depends_on_job_id for j in jobs}

    for start_id in id_set:
        visited: set[int] = set()
        current: int | None = start_id
        while current is not None:
            if current in visited:
                errors.append(f"Circular dependency detected involving job #{start_id}")
                break
            visited.add(current)
            current = edges.get(current)  # None if no dependency

    return errors


# ── Scheduling preview ────────────────────────────────────────────────────────

async def get_schedule_preview(campaign_id: int) -> list[dict]:
    """
    Return a timeline of when each job is expected to run,
    sorted by scheduled_time (None = run ASAP, treated as now).
    """
    async with AsyncSessionLocal() as db:
        jobs = await repo.list_campaign_jobs(db, campaign_id)

    now = datetime.now(timezone.utc)
    preview = []
    for j in sorted(jobs, key=lambda x: (x.scheduled_time or now, x.priority)):
        preview.append({
            "id": j.id,
            "platform": j.platform,
            "priority": j.priority,
            "scheduled_time": j.scheduled_time.isoformat() if j.scheduled_time else None,
            "depends_on": j.depends_on_job_id,
            "status": j.status,
        })
    return preview


# ── Validation ────────────────────────────────────────────────────────────────

async def validate_campaign(campaign_id: int) -> dict:
    """
    Validate a campaign before starting it.

    Checks:
    - At least one job
    - All devices exist
    - No circular dependencies
    - Jobs with tiktok platform have video_path in job_config (warning only)
    - Jobs with youtube_create have video_prompt available (warning only)
    """
    import json as _json
    errors: list[str] = []
    warnings: list[str] = []

    async with AsyncSessionLocal() as db:
        c = await repo.get_campaign(db, campaign_id)
        if not c:
            return {"valid": False, "errors": ["Campaign not found"], "warnings": []}

        jobs = await repo.list_campaign_jobs(db, campaign_id)
        if not jobs:
            errors.append("Campaign has no jobs")
            return {"valid": False, "errors": errors, "warnings": warnings}

        # Dependency check
        dep_errors = validate_dependencies(jobs)
        errors.extend(dep_errors)

        # Device check
        from app.devices.registry import get_device
        for j in jobs:
            if not j.device_id:
                errors.append(f"Job #{j.id}: no device assigned")
            else:
                device = await get_device(db, j.device_id)
                if not device:
                    errors.append(f"Job #{j.id}: device '{j.device_id}' not found")

            # Platform-specific config warnings
            config = _json.loads(j.job_config_json or "{}")
            if j.platform == "tiktok" and not config.get("video_path") and not j.content_job_id:
                warnings.append(f"Job #{j.id} (TikTok): no video_path or content_job_id")
            if j.platform == "youtube_create" and not config.get("video_prompt") and not j.content_job_id:
                warnings.append(f"Job #{j.id} (YouTube Create): no video_prompt or content_job_id")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}
