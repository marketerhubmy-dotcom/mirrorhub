"""
Queue Engine — in-memory sorted queue backed by the ExecutionQueue DB table.

The queue is the single source of truth for what runs next.
On startup it restores all non-terminal entries from the DB so the queue
survives application restarts.

Queue entry lifecycle:
    WAITING → READY → RUNNING → COMPLETED
                            └→ FAILED → RETRY → READY → …
    Any state → PAUSED → WAITING/READY (on resume)
    Any state → CANCELLED
"""
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime

from app.models.database import AsyncSessionLocal
from . import repository as repo

# ── Status constants ──────────────────────────────────────────────────────────

QUEUE_WAITING   = "WAITING"
QUEUE_READY     = "READY"
QUEUE_RUNNING   = "RUNNING"
QUEUE_PAUSED    = "PAUSED"
QUEUE_RETRY     = "RETRY"
QUEUE_COMPLETED = "COMPLETED"
QUEUE_CANCELLED = "CANCELLED"
QUEUE_FAILED    = "FAILED"

TERMINAL_STATUSES = {QUEUE_COMPLETED, QUEUE_CANCELLED, QUEUE_FAILED}

# ── In-memory entry ───────────────────────────────────────────────────────────

@dataclass(order=True)
class QueueEntry:
    """Sortable in-memory representation of one queue slot."""
    sort_key: tuple = field(compare=True, default=(2, 0))  # (priority, queue_order)
    entry_id: int = field(compare=False, default=0)
    campaign_job_id: int = field(compare=False, default=0)
    status: str = field(compare=False, default=QUEUE_WAITING)

    @classmethod
    def from_db(cls, db_entry, priority: int = 2) -> "QueueEntry":
        return cls(
            sort_key=(priority, db_entry.queue_order),
            entry_id=db_entry.id,
            campaign_job_id=db_entry.campaign_job_id,
            status=db_entry.status,
        )


# ── QueueEngine ───────────────────────────────────────────────────────────────

class QueueEngine:
    """
    In-memory priority queue backed by SQLite.

    Sort order: (priority ASC, queue_order ASC) — lower numbers run first.
    Priority: 0=critical, 1=high, 2=normal, 3=low.
    """

    def __init__(self) -> None:
        self._entries: list[QueueEntry] = []
        self._lock = asyncio.Lock()
        self._paused = False  # global queue pause

    # ── Startup ───────────────────────────────────────────────────────────────

    async def restore_from_db(self) -> None:
        """
        Called once at application startup.

        Loads all non-terminal queue entries.  Any RUNNING entry is moved
        back to READY so it gets re-dispatched (crash recovery).
        """
        async with AsyncSessionLocal() as db:
            entries = await repo.list_active_queue(db)
            for entry in entries:
                # Crash recovery: treat RUNNING as READY
                status = entry.status
                if status == QUEUE_RUNNING:
                    await repo.update_queue_entry_status(db, entry.id, QUEUE_READY)
                    status = QUEUE_READY

                cj = await repo.get_campaign_job(db, entry.campaign_job_id)
                priority = cj.priority if cj else 2
                qe = QueueEntry.from_db(entry, priority)
                qe.status = status
                self._entries.append(qe)

        self._entries.sort()

    # ── Enqueue / dequeue ─────────────────────────────────────────────────────

    async def add(self, campaign_job_id: int, priority: int = 2) -> int:
        """Add a CampaignJob to the queue. Returns the new ExecutionQueue.id."""
        async with self._lock:
            async with AsyncSessionLocal() as db:
                # queue_order = current max + 1
                current = await repo.list_active_queue(db)
                order = max((e.queue_order for e in current), default=0) + 1
                entry = await repo.enqueue(db, campaign_job_id, queue_order=order)

            qe = QueueEntry(
                sort_key=(priority, order),
                entry_id=entry.id,
                campaign_job_id=campaign_job_id,
                status=QUEUE_WAITING,
            )
            self._entries.append(qe)
            self._entries.sort()
            return entry.id

    async def next_ready(self) -> QueueEntry | None:
        """Return the highest-priority READY entry without removing it."""
        if self._paused:
            return None
        for qe in self._entries:
            if qe.status == QUEUE_READY:
                return qe
        return None

    async def promote_waiting_to_ready(self, entry_id: int) -> None:
        """Mark a WAITING entry as READY (called by scheduler)."""
        async with AsyncSessionLocal() as db:
            await repo.update_queue_entry_status(db, entry_id, QUEUE_READY)
        for qe in self._entries:
            if qe.entry_id == entry_id and qe.status == QUEUE_WAITING:
                qe.status = QUEUE_READY
                break

    async def mark_running(self, entry_id: int) -> None:
        async with AsyncSessionLocal() as db:
            await repo.update_queue_entry_status(db, entry_id, QUEUE_RUNNING)
        for qe in self._entries:
            if qe.entry_id == entry_id:
                qe.status = QUEUE_RUNNING
                break

    async def mark_completed(self, entry_id: int) -> None:
        async with AsyncSessionLocal() as db:
            await repo.update_queue_entry_status(db, entry_id, QUEUE_COMPLETED)
        self._entries = [qe for qe in self._entries if qe.entry_id != entry_id]

    async def mark_failed(self, entry_id: int) -> None:
        async with AsyncSessionLocal() as db:
            await repo.update_queue_entry_status(db, entry_id, QUEUE_FAILED)
        self._entries = [qe for qe in self._entries if qe.entry_id != entry_id]

    async def mark_retry(self, entry_id: int) -> None:
        """Put back as RETRY (will be promoted to READY after retry delay)."""
        async with AsyncSessionLocal() as db:
            await repo.update_queue_entry_status(db, entry_id, QUEUE_RETRY)
        for qe in self._entries:
            if qe.entry_id == entry_id:
                qe.status = QUEUE_RETRY
                break

    async def promote_retry(self, entry_id: int) -> None:
        """After retry delay, promote RETRY → READY."""
        await self.promote_waiting_to_ready(entry_id)
        for qe in self._entries:
            if qe.entry_id == entry_id:
                qe.status = QUEUE_READY
                break

    # ── Pause / resume ────────────────────────────────────────────────────────

    def pause_queue(self) -> None:
        self._paused = True

    def resume_queue(self) -> None:
        self._paused = False

    async def pause_entry(self, entry_id: int) -> None:
        async with AsyncSessionLocal() as db:
            await repo.update_queue_entry_status(db, entry_id, QUEUE_PAUSED)
        for qe in self._entries:
            if qe.entry_id == entry_id:
                qe.status = QUEUE_PAUSED
                break

    async def resume_entry(self, entry_id: int) -> None:
        await self.promote_waiting_to_ready(entry_id)
        for qe in self._entries:
            if qe.entry_id == entry_id:
                qe.status = QUEUE_READY
                break

    async def cancel_entry(self, entry_id: int) -> None:
        async with AsyncSessionLocal() as db:
            await repo.update_queue_entry_status(db, entry_id, QUEUE_CANCELLED)
        self._entries = [qe for qe in self._entries if qe.entry_id != entry_id]

    # ── Reorder ───────────────────────────────────────────────────────────────

    async def reorder(self, campaign_job_id: int, new_order: int) -> None:
        async with AsyncSessionLocal() as db:
            await repo.reorder_queue_entry(db, campaign_job_id, new_order)
        for qe in self._entries:
            if qe.campaign_job_id == campaign_job_id:
                qe.sort_key = (qe.sort_key[0], new_order)
                break
        self._entries.sort()

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> list[dict]:
        return [
            {
                "entry_id": qe.entry_id,
                "campaign_job_id": qe.campaign_job_id,
                "status": qe.status,
                "priority": qe.sort_key[0],
                "queue_order": qe.sort_key[1],
            }
            for qe in self._entries
        ]

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for qe in self._entries:
            result[qe.status] = result.get(qe.status, 0) + 1
        return result

    @property
    def is_paused(self) -> bool:
        return self._paused


# Singleton used throughout the campaign module
queue_engine = QueueEngine()
