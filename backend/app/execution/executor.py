import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from app.models.database import AsyncSessionLocal
from app.utils.paths import _BACKEND_ROOT
from .state_machine import ExecutionState, ExecutionStatus, StepResult, StepState
from .progress import broadcast_state, capture_screenshot
from .device_session import set_active_job, clear_active_job
from . import youtube_create as ytc
from . import tiktok as ttk

_states: dict[int, ExecutionState] = {}    # job_id -> live state
_engines: dict[int, "ExecutionEngine"] = {}  # job_id -> engine

STEP_HANDLERS: dict = {**ytc.HANDLERS, **ttk.HANDLERS}

# Steps that park the pipeline for human review (STOP_BEFORE_POST mode)
_REVIEW_STOP_STEPS = frozenset({"tiktok_pre_publish_check"})

LOG_DIR = _BACKEND_ROOT / "logs"


def get_state(job_id: int) -> ExecutionState | None:
    return _states.get(job_id)


def get_engine(job_id: int) -> "ExecutionEngine | None":
    return _engines.get(job_id)


class ExecutionEngine:
    def __init__(self, state: ExecutionState, adb_address: str, db_job_id: int):
        self.state = state
        self.adb_address = adb_address
        self.db_job_id = db_job_id
        self._paused = False
        self._cancelled = False

    # ── Diagnostic log ────────────────────────────────────────────────────────

    def _write_diag(self, step: StepState, result: str, error: str | None = None) -> None:
        """Append one structured line to backend/logs/pipeline_{job_id}.log."""
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_file = LOG_DIR / f"pipeline_{self.state.job_id}.log"
            ts = datetime.now(timezone.utc).isoformat()
            screenshot = step.screenshot or ""
            entry = (
                f"{ts} | "
                f"device={self.state.device_id} | "
                f"step[{step.index}] {step.step_type!r} | "
                f"label={step.label!r} | "
                f"result={result} | "
                f"error={repr(error or '')} | "
                f"screenshot={screenshot}\n"
            )
            with open(log_file, "a", encoding="utf-8") as fh:
                fh.write(entry)
        except Exception:
            pass  # diagnostic failure must never break execution

    # ── Main execution loop ───────────────────────────────────────────────────

    async def run(self, steps: list[dict]) -> None:
        self.state.status = ExecutionStatus.RUNNING
        self.state.started_at = datetime.now(timezone.utc)
        total = len(steps)

        for i, step_def in enumerate(steps):
            if self._cancelled:
                self.state.status = ExecutionStatus.CANCELLED
                self.state.add_log("Execution dibatalkan.", "warn")
                break

            while self._paused:
                await asyncio.sleep(0.5)

            step_state = self.state.steps[i]
            step_state.status = "running"
            step_state.started_at = datetime.now(timezone.utc)
            self.state.current_index = i
            self.state.progress = round(i / total * 100, 1)
            self.state.add_log(f"▶ {step_state.label}")
            await broadcast_state(self.state)
            await self._persist()

            handler = STEP_HANDLERS.get(step_def["type"])
            if not handler:
                step_state.status = "skipped"
                self.state.add_log(f"⚠ Unknown step: {step_def['type']}", "warn")
                self._write_diag(step_state, "SKIPPED")
                await broadcast_state(self.state)
                continue

            max_retries = step_def.get("retry_max", 2)
            final_result = StepResult.ABORT

            for attempt in range(max_retries + 1):
                try:
                    result = await handler(self.adb_address, step_def)
                except Exception as exc:
                    self.state.add_log(
                        f"❌ {step_state.label} attempt {attempt + 1}: {exc}", "error"
                    )
                    result = StepResult.RETRY

                if result == StepResult.SUCCESS:
                    final_result = StepResult.SUCCESS
                    break
                elif result == StepResult.SKIP:
                    final_result = StepResult.SKIP
                    break
                elif result == StepResult.RETRY and attempt < max_retries:
                    self.state.add_log(
                        f"↩ Retry {step_state.label} ({attempt + 1}/{max_retries})", "warn"
                    )
                    screenshot = await capture_screenshot(
                        self.adb_address, self.state.job_id, step_state.label
                    )
                    if screenshot:
                        step_state.screenshot = screenshot
                        self.state.last_screenshot = screenshot
                    await broadcast_state(self.state)
                    await asyncio.sleep(2)
                else:
                    final_result = StepResult.ABORT
                    break

            step_state.completed_at = datetime.now(timezone.utc)

            if final_result in (StepResult.SUCCESS, StepResult.SKIP):
                step_state.status = (
                    "success" if final_result == StepResult.SUCCESS else "skipped"
                )
                self.state.add_log(f"✓ {step_state.label}", "success")
                self._write_diag(step_state, final_result.value)
            else:
                step_state.status = "failed"
                step_state.error = f"Gagal selepas {max_retries + 1} percubaan"
                screenshot = await capture_screenshot(
                    self.adb_address, self.state.job_id, step_state.label
                )
                if screenshot:
                    step_state.screenshot = screenshot
                    self.state.last_screenshot = screenshot
                self.state.status = ExecutionStatus.FAILED
                self.state.error = (
                    f"'{step_state.label}' gagal selepas {max_retries + 1} percubaan"
                )
                self.state.add_log(f"❌ ABORT: {step_state.label}", "error")
                self._write_diag(step_state, "FAILED", step_state.error)
                await broadcast_state(self.state)
                await self._persist()
                break

            await broadcast_state(self.state)
            await asyncio.sleep(0.3)

        # ── Resolve final status ──────────────────────────────────────────────
        if self.state.status == ExecutionStatus.RUNNING:
            # Find the last step that completed successfully
            last_ok_type: str | None = None
            for ss in reversed(self.state.steps):
                if ss.status == "success":
                    last_ok_type = ss.step_type
                    break

            if last_ok_type in _REVIEW_STOP_STEPS:
                # publish_mode == "manual": parked at the Publish button
                self.state.status = ExecutionStatus.READY_FOR_REVIEW
                self.state.progress = 100.0
                self.state.add_log(
                    "⏸ Pipeline selesai — menunggu review sebelum Post. "
                    "Tekan butang Publish pada phone apabila sedia.",
                    "success",
                )
            else:
                self.state.status = ExecutionStatus.COMPLETED
                self.state.progress = 100.0
                self.state.add_log("✅ Execution selesai!", "success")

        self.state.completed_at = datetime.now(timezone.utc)
        await broadcast_state(self.state)
        await self._persist()
        clear_active_job(self.state.device_id)
        _engines.pop(self.state.job_id, None)

    # ── DB persistence ────────────────────────────────────────────────────────

    async def _persist(self) -> None:
        from .models import ExecutionJob
        try:
            async with AsyncSessionLocal() as db:
                job = await db.get(ExecutionJob, self.db_job_id)
                if job:
                    job.status = self.state.status.value
                    job.progress = self.state.progress
                    job.current_step = (
                        self.state.current_step.label if self.state.current_step else None
                    )
                    job.error = self.state.error
                    job.last_screenshot = self.state.last_screenshot
                    job.logs = json.dumps(self.state.logs[-100:])
                    job.updated_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass

    def pause(self) -> None:
        self._paused = True
        self.state.add_log("⏸ Execution dijeda.", "info")

    def resume(self) -> None:
        self._paused = False
        self.state.add_log("▶ Execution disambung.", "info")

    def cancel(self) -> None:
        self._cancelled = True


async def start_execution(
    job_id: int,
    device_id: str,
    adb_address: str,
    steps: list[dict],
) -> ExecutionState:
    state = ExecutionState(
        job_id=job_id,
        device_id=device_id,
        status=ExecutionStatus.STARTING,
        steps=[
            StepState(index=i, label=s.get("label", s["type"]), step_type=s["type"])
            for i, s in enumerate(steps)
        ],
    )
    _states[job_id] = state
    engine = ExecutionEngine(state, adb_address, job_id)
    _engines[job_id] = engine
    set_active_job(device_id, job_id)
    asyncio.create_task(engine.run(steps))
    return state
