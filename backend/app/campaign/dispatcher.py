"""
Campaign Dispatcher — the main background loop.

Lifecycle:
  1. tick() runs every POLL_INTERVAL seconds
  2. Scheduler promotes WAITING → READY based on time/deps
  3. Dispatcher picks the highest-priority READY entry
  4. Verifies the target device is available
  5. Dispatches via campaign_executor.dispatch()
  6. Background watcher waits for execution to finish
  7. On completion: updates queue, records history, checks recurrence
  8. Broadcasts queue state via WebSocket

The Execution Engine is never called directly from here.
All execution goes through the plugin interface (YouTubeCreatePlugin,
TikTokPlugin, etc.) via campaign_executor.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.models.database import AsyncSessionLocal
from app.execution.device_session import try_claim_device, clear_active_job
from . import repository as repo, scheduler as sched
from .queue import queue_engine, QUEUE_COMPLETED, QUEUE_FAILED

logger = logging.getLogger(__name__)

_running = False


# ── Broadcast helper (non-blocking) ──────────────────────────────────────────

async def _broadcast_queue() -> None:
    try:
        from app.websocket.manager import manager
        import json as _json
        data = _json.dumps({
            "event": "queue_update",
            "queue": queue_engine.snapshot(),
            "counts": queue_engine.counts(),
        })
        await manager.broadcast_campaign("queue", data)
    except Exception:
        pass


async def _broadcast_campaign(campaign_id: int) -> None:
    try:
        from app.websocket.manager import manager
        import json as _json
        async with AsyncSessionLocal() as db:
            c = await repo.get_campaign(db, campaign_id)
            if not c:
                return
            data = _json.dumps({"event": "campaign_update", "campaign": c.to_dict()})
        await manager.broadcast_campaign(str(campaign_id), data)
    except Exception:
        pass


# ── Execution watcher ─────────────────────────────────────────────────────────

async def _watch_execution(
    entry_id: int,
    campaign_job_id: int,
    campaign_id: int,
    execution_job_id: int,
    started_at: datetime,
) -> None:
    """
    Poll the Execution Engine state until the job finishes.
    Then update queue + campaign + history accordingly.
    """
    from app.execution import executor as eng

    while True:
        await asyncio.sleep(3.0)
        state = eng.get_state(execution_job_id)

        # Engine dropped the state (completed/failed long ago) — check DB
        if not state:
            async with AsyncSessionLocal() as db:
                from app.execution.models import ExecutionJob
                db_job = await db.get(ExecutionJob, execution_job_id)
                if not db_job:
                    break
                final_status = db_job.status
            _handle_terminal(final_status, entry_id, campaign_job_id, campaign_id, started_at)
            break

        if state.status.value in ("COMPLETED", "FAILED", "CANCELLED"):
            _handle_terminal(state.status.value, entry_id, campaign_job_id, campaign_id, started_at)
            break


def _handle_terminal(
    exec_status: str,
    entry_id: int,
    campaign_job_id: int,
    campaign_id: int,
    started_at: datetime,
) -> None:
    """Schedule the async terminal handling as a background task."""
    asyncio.create_task(
        _finish_job(exec_status, entry_id, campaign_job_id, campaign_id, started_at)
    )


async def _finish_job(
    exec_status: str,
    entry_id: int,
    campaign_job_id: int,
    campaign_id: int,
    started_at: datetime,
) -> None:
    duration = (datetime.now(timezone.utc) - started_at).total_seconds()
    success = exec_status == "COMPLETED"

    async with AsyncSessionLocal() as db:
        cj = await repo.get_campaign_job(db, campaign_job_id)
        if not cj:
            return

        if success:
            await repo.set_campaign_job_status(db, campaign_job_id, "COMPLETED")
            await queue_engine.mark_completed(entry_id)
            await repo.record_history(
                db, "COMPLETED",
                campaign_id=campaign_id, campaign_job_id=campaign_job_id,
                result="OK", detail=f"Execution finished", duration_s=duration,
            )
            await sched.schedule_next_recurrence(campaign_job_id)

        else:
            if cj.retry_count < cj.retry_max:
                # Schedule a retry
                await repo.set_campaign_job_status(db, campaign_job_id, "RETRY")
                cj.retry_count = (cj.retry_count or 0) + 1
                cj.updated_at = datetime.now(timezone.utc)
                await db.commit()
                await queue_engine.mark_retry(entry_id)
                await repo.record_history(
                    db, "RETRIED",
                    campaign_id=campaign_id, campaign_job_id=campaign_job_id,
                    result="RETRY", detail=f"Attempt {cj.retry_count}/{cj.retry_max}",
                    duration_s=duration,
                )
                asyncio.create_task(_retry_after_delay(entry_id))
            else:
                # Give up
                await repo.set_campaign_job_status(db, campaign_job_id, "FAILED",
                                                   error=f"Exhausted {cj.retry_max} retries")
                await queue_engine.mark_failed(entry_id)
                await repo.record_history(
                    db, "FAILED",
                    campaign_id=campaign_id, campaign_job_id=campaign_job_id,
                    result="FAIL", detail="All retries exhausted", duration_s=duration,
                )

        await repo.refresh_campaign_counts(db, campaign_id)

    await _broadcast_queue()
    await _broadcast_campaign(campaign_id)
    await _check_campaign_complete(campaign_id)


async def _retry_after_delay(entry_id: int) -> None:
    await asyncio.sleep(settings.campaign_retry_delay)
    await queue_engine.promote_retry(entry_id)
    await _broadcast_queue()


async def _check_campaign_complete(campaign_id: int) -> None:
    """Mark campaign COMPLETED or FAILED when no active jobs remain."""
    async with AsyncSessionLocal() as db:
        jobs = await repo.list_campaign_jobs(db, campaign_id)
        active = [j for j in jobs if j.status in ("WAITING", "READY", "RUNNING", "RETRY", "PAUSED")]
        if active:
            return
        failed = [j for j in jobs if j.status == "FAILED"]
        c = await repo.get_campaign(db, campaign_id)
        if c and c.status == "RUNNING":
            new_status = "FAILED" if failed else "COMPLETED"
            c.status = new_status
            c.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await repo.record_history(
                db, new_status,
                campaign_id=campaign_id,
                result=new_status,
                detail=f"Campaign finished with {len(failed)} failed job(s)",
            )
    await _broadcast_campaign(campaign_id)


# ── Main dispatch loop ────────────────────────────────────────────────────────

async def _tick() -> None:
    """Single dispatcher tick: promote → dispatch."""
    # 1. Scheduler: promote WAITING → READY
    promoted = await sched.tick()
    if promoted:
        await _broadcast_queue()

    # 2. Pick next READY job
    next_entry = await queue_engine.next_ready()
    if not next_entry:
        return

    async with AsyncSessionLocal() as db:
        cj = await repo.get_campaign_job(db, next_entry.campaign_job_id)
        if not cj:
            await queue_engine.cancel_entry(next_entry.entry_id)
            return

        # 3. Atomically claim device — prevents double-dispatch across concurrent ticks
        device_id = cj.device_id
        if not await try_claim_device(device_id, next_entry.entry_id):
            return  # device busy, try again next tick

        # 4. Check device is known; release claim on failure
        from app.devices.registry import get_device
        device = await get_device(db, device_id)
        if not device or not device.adb_address:
            clear_active_job(device_id)
            return

        # 5. Mark running
        await queue_engine.mark_running(next_entry.entry_id)
        await repo.set_campaign_job_status(db, cj.id, "RUNNING")

    # 6. Dispatch (outside the session so the session isn't held during execution)
    from . import executor as camp_exec
    started_at = datetime.now(timezone.utc)
    try:
        result = await camp_exec.dispatch(cj, device)
    except Exception as exc:
        logger.exception("Dispatcher: dispatch() raised: %s", exc)
        clear_active_job(cj.device_id)
        async with AsyncSessionLocal() as db:
            await repo.set_campaign_job_status(db, cj.id, "RETRY", error=str(exc))
        await queue_engine.mark_retry(next_entry.entry_id)
        await asyncio.sleep(settings.campaign_retry_delay)
        await queue_engine.promote_retry(next_entry.entry_id)
        await _broadcast_queue()
        return

    # 7. Spawn watcher
    if result.success and result.job_id:
        asyncio.create_task(
            _watch_execution(
                next_entry.entry_id, cj.id, cj.campaign_id,
                result.job_id, started_at,
            )
        )
    else:
        # Dispatch failed immediately (validation error, no device, etc.)
        async with AsyncSessionLocal() as db:
            await repo.set_campaign_job_status(db, cj.id, "FAILED", error=result.reason)
        await queue_engine.mark_failed(next_entry.entry_id)
        async with AsyncSessionLocal() as db:
            await repo.record_history(
                db, "FAILED",
                campaign_id=cj.campaign_id, campaign_job_id=cj.id,
                result="FAIL", detail=result.reason,
            )
        await _broadcast_queue()
        await _broadcast_campaign(cj.campaign_id)

    await _broadcast_queue()


async def run_loop() -> None:
    """Start the dispatcher background loop. Called once from app lifespan."""
    global _running
    _running = True
    logger.info("Campaign dispatcher started")
    await queue_engine.restore_from_db()
    while _running:
        try:
            await _tick()
        except Exception:
            logger.exception("Dispatcher tick error")
        await asyncio.sleep(settings.campaign_poll_interval)


def stop() -> None:
    global _running
    _running = False
