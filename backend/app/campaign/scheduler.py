"""
Campaign Scheduler.

Responsibilities:
- Determine if a WAITING CampaignJob is ready to run based on:
    1. scheduled_time (run at or after this datetime)
    2. depends_on_job_id (dependency must be COMPLETED)
    3. Recurring schedule expression (compute next run, re-enqueue after done)
- Promote eligible WAITING entries to READY in the queue

Recurring schedule_expr format (stored as JSON in CampaignJob.schedule_expr):
    {"type": "hourly"}
    {"type": "daily",   "time": "09:00", "tz": "UTC"}
    {"type": "weekly",  "day": "monday", "time": "09:00", "tz": "UTC"}
    {"type": "monthly", "day": 1,        "time": "09:00", "tz": "UTC"}

Timezone strings are standard zoneinfo names (e.g. "Asia/Kuala_Lumpur").
We only use stdlib datetime — no external cron libraries required.
"""
import json
from datetime import datetime, timedelta, timezone

from app.models.database import AsyncSessionLocal
from .models import CampaignJob, ExecutionQueue
from . import repository as repo
from .queue import queue_engine, QUEUE_WAITING, QUEUE_RETRY


async def tick() -> list[int]:
    """
    Single scheduler tick.

    Check every WAITING/RETRY queue entry against its CampaignJob's
    scheduled_time and dependency.  Return list of entry_ids promoted.
    """
    promoted: list[int] = []
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # Fetch all WAITING and RETRY entries with their CampaignJob
        entries = await repo.list_active_queue(db)
        for entry in entries:
            if entry.status not in (QUEUE_WAITING, QUEUE_RETRY):
                continue

            cj = await repo.get_campaign_job(db, entry.campaign_job_id)
            if not cj:
                continue

            # ── scheduled_time check ──────────────────────────────────────
            if cj.scheduled_time and cj.scheduled_time > now:
                continue  # too early

            # ── dependency check ──────────────────────────────────────────
            if cj.depends_on_job_id:
                dep = await repo.get_campaign_job(db, cj.depends_on_job_id)
                if not dep or dep.status != "COMPLETED":
                    continue  # dependency not satisfied

            # ── promote ───────────────────────────────────────────────────
            await queue_engine.promote_waiting_to_ready(entry.id)
            promoted.append(entry.id)

    return promoted


async def schedule_next_recurrence(campaign_job_id: int) -> None:
    """
    If the CampaignJob has a recurring schedule_expr, create a new
    CampaignJob (copy) with the next calculated scheduled_time.
    """
    async with AsyncSessionLocal() as db:
        cj = await repo.get_campaign_job(db, campaign_job_id)
        if not cj or not cj.schedule_expr:
            return

        expr = json.loads(cj.schedule_expr)
        next_time = _compute_next(expr)
        if not next_time:
            return

        from .schemas import CampaignJobCreate
        new_data = CampaignJobCreate(
            campaign_id=cj.campaign_id,
            content_job_id=cj.content_job_id,
            platform=cj.platform,
            device_id=cj.device_id,
            priority=cj.priority,
            scheduled_time=next_time,
            schedule_expr=expr,
            depends_on_job_id=None,
            retry_max=cj.retry_max,
            job_config=json.loads(cj.job_config_json or "{}"),
        )
        new_cj = await repo.create_campaign_job(db, new_data)
        await queue_engine.add(new_cj.id, priority=new_cj.priority)


def _compute_next(expr: dict) -> datetime | None:
    """Compute the next fire datetime from a schedule_expr dict."""
    now = datetime.now(timezone.utc)
    sched_type = expr.get("type", "")
    time_str = expr.get("time", "00:00")
    try:
        h, m = (int(x) for x in time_str.split(":"))
    except Exception:
        h, m = 0, 0

    if sched_type == "hourly":
        return now + timedelta(hours=1)

    if sched_type == "daily":
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    if sched_type == "weekly":
        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                   "friday": 4, "saturday": 5, "sunday": 6}
        target_dow = day_map.get(str(expr.get("day", "monday")).lower(), 0)
        days_ahead = (target_dow - now.weekday()) % 7 or 7
        candidate = (now + timedelta(days=days_ahead)).replace(
            hour=h, minute=m, second=0, microsecond=0
        )
        return candidate

    if sched_type == "monthly":
        day = int(expr.get("day", 1))
        candidate = now.replace(day=day, hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            # advance to next month
            if now.month == 12:
                candidate = candidate.replace(year=now.year + 1, month=1)
            else:
                candidate = candidate.replace(month=now.month + 1)
        return candidate

    return None
