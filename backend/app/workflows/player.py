"""
Workflow Player.

Reads WorkflowStep objects from the DB, resolves {{variables}}, checks
conditions via Vision Engine, and executes each step via ADB.

This is a standalone executor — independent of the Execution Engine.
It tracks progress in the WorkflowExecution table and broadcasts via WS.

Public API:
    play_workflow(workflow_id, device_id, adb_address, variables, simulate)
        → WorkflowExecution
"""
import asyncio
import json
import re
import subprocess
from datetime import datetime, timezone
from app.utils.adb_path import ADB
from app.models.database import AsyncSessionLocal
from app.websocket.manager import manager
from .models import WorkflowExecution, WorkflowStep

_runs: dict[int, "WorkflowRunner"] = {}   # execution_id → runner

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


async def _run_adb(adb_address: str, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        str(ADB), "-s", adb_address, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    out, _ = await proc.communicate()
    return out.decode(errors="replace")


def _resolve(value: str, variables: dict) -> str:
    """Replace {{var}} tokens with values from the variables dict."""
    return _VAR_RE.sub(lambda m: str(variables.get(m.group(1), "")), value)


def _resolve_params(params: dict, variables: dict) -> dict:
    """Recursively resolve variables in all string parameter values."""
    result = {}
    for k, v in params.items():
        if isinstance(v, str):
            result[k] = _resolve(v, variables)
        elif isinstance(v, dict):
            result[k] = _resolve_params(v, variables)
        else:
            result[k] = v
    return result


async def _check_condition(adb_address: str, device_id: str, conditions: dict) -> bool:
    """
    Evaluate step conditions.  Returns True = proceed, False = skip this step.

    Supported keys:
        if_button_exists  str   — proceed only if button is visible
        if_screen         str   — proceed only if on this screen
        if_not_button     str   — proceed only if button is NOT visible
        skip_if_missing   bool  — skip (not fail) when condition is False
    """
    if not conditions:
        return True
    if not device_id:
        return True

    try:
        from app.vision.analyzer import analyze_screen
        analysis = await analyze_screen(adb_address, device_id, use_cache_ms=3000)
    except Exception:
        return True  # no vision — proceed anyway

    if "if_button_exists" in conditions:
        if not analysis.has_button(conditions["if_button_exists"]):
            return False

    if "if_not_button" in conditions:
        if analysis.has_button(conditions["if_not_button"]):
            return False

    if "if_screen" in conditions:
        wanted = conditions["if_screen"].lower()
        if analysis.screen_name.lower() != wanted and analysis.screen_type.value.lower() != wanted:
            return False

    return True


# ── Step handlers ──────────────────────────────────────────────────────────────

async def _tap_button(adb_address: str, device_id: str, params: dict) -> str:
    button = params.get("button", "")
    if device_id:
        from app.vision.analyzer import analyze_screen
        from app.vision.matcher import find_button
        analysis = await analyze_screen(adb_address, device_id, use_cache_ms=1000)
        btn = find_button(analysis, button)
        if btn and btn.x > 0 and btn.y > 0:
            await _run_adb(adb_address, "shell", "input", "tap", str(btn.x), str(btn.y))
            return "SUCCESS"
    # fallback: relative tap
    rx = float(params.get("fallback_rx", 0.5))
    ry = float(params.get("fallback_ry", 0.5))
    raw = await _run_adb(adb_address, "shell", "wm", "size")
    try:
        part = raw.strip().split(":")[-1].strip()
        w, h = (int(x) for x in part.split("x"))
    except Exception:
        w, h = 1080, 2400
    await _run_adb(adb_address, "shell", "input", "tap", str(int(w * rx)), str(int(h * ry)))
    return "SUCCESS"


async def _tap_relative(adb_address: str, _: str, params: dict) -> str:
    rx, ry = float(params.get("rx", 0.5)), float(params.get("ry", 0.5))
    raw = await _run_adb(adb_address, "shell", "wm", "size")
    try:
        part = raw.strip().split(":")[-1].strip()
        w, h = (int(x) for x in part.split("x"))
    except Exception:
        w, h = 1080, 2400
    await _run_adb(adb_address, "shell", "input", "tap", str(int(w * rx)), str(int(h * ry)))
    return "SUCCESS"


async def _input_text(adb_address: str, _: str, params: dict) -> str:
    text = str(params.get("text", ""))
    safe = (text.replace("\\", "").replace('"', "'").replace("`", "'")
                .replace("$", "").replace("(", "").replace(")", "")
                .replace("&", "dan").replace("<", "").replace(">", ""))
    for line in safe.split("\n"):
        if line.strip():
            await _run_adb(adb_address, "shell", "input", "text", line.replace(" ", "%s"))
        await _run_adb(adb_address, "shell", "input", "keyevent", "KEYCODE_ENTER")
        await asyncio.sleep(0.1)
    return "SUCCESS"


async def _paste(adb_address: str, _: str, params: dict) -> str:
    await _run_adb(adb_address, "shell", "input", "keyevent", "KEYCODE_CTRL_LEFT", "KEYCODE_V")
    return "SUCCESS"


async def _long_press(adb_address: str, _: str, params: dict) -> str:
    rx, ry = float(params.get("rx", 0.5)), float(params.get("ry", 0.5))
    dur = int(params.get("duration_ms", 1000))
    raw = await _run_adb(adb_address, "shell", "wm", "size")
    try:
        part = raw.strip().split(":")[-1].strip()
        w, h = (int(x) for x in part.split("x"))
    except Exception:
        w, h = 1080, 2400
    x, y = int(w * rx), int(h * ry)
    await _run_adb(adb_address, "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(dur))
    return "SUCCESS"


async def _swipe(adb_address: str, _: str, params: dict) -> str:
    raw = await _run_adb(adb_address, "shell", "wm", "size")
    try:
        part = raw.strip().split(":")[-1].strip()
        w, h = (int(x) for x in part.split("x"))
    except Exception:
        w, h = 1080, 2400
    x1 = int(w * float(params.get("start_rx", 0.5)))
    y1 = int(h * float(params.get("start_ry", 0.5)))
    x2 = int(w * float(params.get("end_rx", 0.5)))
    y2 = int(h * float(params.get("end_ry", 0.8)))
    dur = int(params.get("duration_ms", 300))
    await _run_adb(adb_address, "shell", "input", "swipe",
                   str(x1), str(y1), str(x2), str(y2), str(dur))
    return "SUCCESS"


async def _scroll(adb_address: str, _: str, params: dict, direction: str) -> str:
    raw = await _run_adb(adb_address, "shell", "wm", "size")
    try:
        part = raw.strip().split(":")[-1].strip()
        w, h = (int(x) for x in part.split("x"))
    except Exception:
        w, h = 1080, 2400
    cx = w // 2
    if direction == "down":
        await _run_adb(adb_address, "shell", "input", "swipe",
                       str(cx), str(int(h * 0.6)), str(cx), str(int(h * 0.3)), "300")
    else:
        await _run_adb(adb_address, "shell", "input", "swipe",
                       str(cx), str(int(h * 0.3)), str(cx), str(int(h * 0.6)), "300")
    return "SUCCESS"


async def _wait(adb_address: str, _: str, params: dict) -> str:
    secs = float(params.get("seconds", 1))
    await asyncio.sleep(secs)
    return "SUCCESS"


async def _wait_until(adb_address: str, device_id: str, params: dict) -> str:
    if not device_id:
        await asyncio.sleep(float(params.get("timeout", 10)))
        return "SUCCESS"
    from app.vision.analyzer import wait_until
    await wait_until(
        adb_address, device_id,
        screen=params.get("screen"),
        button=params.get("button"),
        loading=params.get("loading"),
        timeout=int(params.get("timeout", 30)),
        poll_interval=float(params.get("poll_interval", 3.0)),
    )
    return "SUCCESS"


async def _launch_app(adb_address: str, _: str, params: dict) -> str:
    pkg = params.get("package", "")
    if not pkg:
        return "SKIP"
    await _run_adb(adb_address, "shell", "monkey", "-p", pkg,
                   "-c", "android.intent.category.LAUNCHER", "1")
    return "SUCCESS"


async def _open_activity(adb_address: str, _: str, params: dict) -> str:
    component = params.get("component", "")
    if not component:
        return "SKIP"
    await _run_adb(adb_address, "shell", "am", "start", "-n", component)
    return "SUCCESS"


async def _take_screenshot(adb_address: str, device_id: str, params: dict) -> str:
    if device_id:
        from app.vision.analyzer import analyze_screen
        await analyze_screen(adb_address, device_id)
    return "SUCCESS"


async def _verify_screen(adb_address: str, device_id: str, params: dict) -> str:
    if not device_id:
        return "SUCCESS"
    from app.vision.analyzer import analyze_screen
    analysis = await analyze_screen(adb_address, device_id)
    expected = params.get("screen", "").lower()
    if expected and analysis.screen_name.lower() != expected and analysis.screen_type.value.lower() != expected:
        return "RETRY"
    return "SUCCESS"


async def _verify_button(adb_address: str, device_id: str, params: dict) -> str:
    if not device_id:
        return "SUCCESS"
    from app.vision.analyzer import analyze_screen
    analysis = await analyze_screen(adb_address, device_id, use_cache_ms=1000)
    button = params.get("button", "")
    if button and not analysis.has_button(button):
        return "RETRY"
    return "SUCCESS"


async def _keyevent(adb_address: str, _: str, keycode: str) -> str:
    await _run_adb(adb_address, "shell", "input", "keyevent", keycode)
    return "SUCCESS"


_HANDLERS: dict = {
    "tap_button":      lambda a, d, p: _tap_button(a, d, p),
    "tap_relative":    lambda a, d, p: _tap_relative(a, d, p),
    "input_text":      lambda a, d, p: _input_text(a, d, p),
    "paste":           lambda a, d, p: _paste(a, d, p),
    "long_press":      lambda a, d, p: _long_press(a, d, p),
    "swipe":           lambda a, d, p: _swipe(a, d, p),
    "scroll_down":     lambda a, d, p: _scroll(a, d, p, "down"),
    "scroll_up":       lambda a, d, p: _scroll(a, d, p, "up"),
    "wait":            lambda a, d, p: _wait(a, d, p),
    "delay":           lambda a, d, p: _wait(a, d, p),
    "wait_until":      lambda a, d, p: _wait_until(a, d, p),
    "launch_app":      lambda a, d, p: _launch_app(a, d, p),
    "open_activity":   lambda a, d, p: _open_activity(a, d, p),
    "take_screenshot": lambda a, d, p: _take_screenshot(a, d, p),
    "verify_screen":   lambda a, d, p: _verify_screen(a, d, p),
    "verify_button":   lambda a, d, p: _verify_button(a, d, p),
    "back":            lambda a, d, p: _keyevent(a, d, "KEYCODE_BACK"),
    "home":            lambda a, d, p: _keyevent(a, d, "KEYCODE_HOME"),
    "recent_apps":     lambda a, d, p: _keyevent(a, d, "KEYCODE_APP_SWITCH"),
}


# ── Runner ────────────────────────────────────────────────────────────────────

class WorkflowRunner:
    def __init__(self, execution: WorkflowExecution, steps: list[WorkflowStep],
                 variables: dict, simulate: bool = False):
        self.execution = execution
        self.steps = [s for s in sorted(steps, key=lambda s: s.order) if s.enabled]
        self.variables = variables
        self.simulate = simulate
        self._cancelled = False

    async def run(self) -> None:
        total = len(self.steps)
        adb = self.execution.adb_address
        did = self.execution.device_id
        logs: list[dict] = []

        def log(msg: str, level: str = "info") -> None:
            logs.append({"ts": datetime.now(timezone.utc).isoformat(), "level": level, "message": msg})

        for i, step in enumerate(self.steps):
            if self._cancelled:
                break

            params = _resolve_params(json.loads(step.parameters_json or "{}"), self.variables)
            conditions = json.loads(step.conditions_json or "{}")

            log(f"▶ [{i+1}/{total}] {step.label}")
            await self._persist(status="RUNNING", idx=i, progress=round(i / total * 100, 1),
                                logs=logs)
            await self._broadcast(i, step.label, "running", total, logs)

            if self.simulate:
                log(f"  [sim] {step.step_type} params={params}")
                await self._persist(status="RUNNING", idx=i, progress=round((i+1)/total*100, 1),
                                    logs=logs)
                continue

            # Condition check
            proceed = await _check_condition(adb, did, conditions)
            if not proceed:
                if conditions.get("skip_if_missing", True):
                    log(f"  ⏭ Skipped (condition not met)", "warn")
                    continue
                else:
                    log(f"  ❌ Condition failed — aborting", "error")
                    await self._finish("FAILED", f"Condition failed at step '{step.label}'", logs)
                    return

            handler = _HANDLERS.get(step.step_type)
            if not handler:
                log(f"  ⚠ Unknown step type '{step.step_type}' — skipping", "warn")
                continue

            success = False
            for attempt in range(step.retry_max + 1):
                try:
                    result = await asyncio.wait_for(handler(adb, did, params), timeout=step.timeout)
                    if result in ("SUCCESS", "SKIP"):
                        success = True
                        break
                    if result == "RETRY" and attempt < step.retry_max:
                        log(f"  ↩ Retry {attempt+1}/{step.retry_max}", "warn")
                        await asyncio.sleep(2)
                except asyncio.TimeoutError:
                    log(f"  ⏱ Timeout after {step.timeout}s", "warn")
                    break
                except Exception as exc:
                    log(f"  ❌ Error: {exc}", "error")
                    if attempt >= step.retry_max:
                        break

            if not success and step.retry_max > 0:
                log(f"  ❌ ABORT: '{step.label}' failed after {step.retry_max+1} attempts", "error")
                await self._finish("FAILED", f"'{step.label}' failed", logs)
                return

            log(f"  ✓ {step.label}", "success")
            progress = round((i + 1) / total * 100, 1)
            await self._persist(status="RUNNING", idx=i, progress=progress, logs=logs)
            await self._broadcast(i, step.label, "success", total, logs)
            await asyncio.sleep(0.2)

        status = "CANCELLED" if self._cancelled else "COMPLETED"
        log("✅ Workflow selesai!" if status == "COMPLETED" else "⏹ Cancelled")
        await self._finish(status, None, logs)

    async def _persist(self, status: str, idx: int, progress: float, logs: list) -> None:
        try:
            async with AsyncSessionLocal() as db:
                exc = await db.get(WorkflowExecution, self.execution.id)
                if exc:
                    exc.status = status
                    exc.current_step_index = idx
                    exc.progress = progress
                    exc.logs_json = json.dumps(logs[-100:])
                    await db.commit()
        except Exception:
            pass

    async def _finish(self, status: str, error: str | None, logs: list) -> None:
        try:
            async with AsyncSessionLocal() as db:
                exc = await db.get(WorkflowExecution, self.execution.id)
                if exc:
                    exc.status = status
                    exc.error = error
                    exc.finished_at = datetime.now(timezone.utc)
                    exc.progress = 100.0 if status == "COMPLETED" else exc.progress
                    exc.logs_json = json.dumps(logs[-100:])
                    await db.commit()
        except Exception:
            pass
        _runs.pop(self.execution.id, None)
        data = json.dumps({
            "type": "workflow_done",
            "execution_id": self.execution.id,
            "status": status,
        })
        await manager.broadcast_workflow(str(self.execution.workflow_id), data)

    async def _broadcast(self, idx: int, label: str, step_status: str,
                         total: int, logs: list) -> None:
        data = json.dumps({
            "type": "workflow_progress",
            "execution_id": self.execution.id,
            "current_step": idx,
            "step_label": label,
            "step_status": step_status,
            "total_steps": total,
            "progress": round(idx / total * 100, 1),
            "logs": logs[-10:],
        })
        await manager.broadcast_workflow(str(self.execution.workflow_id), data)

    def cancel(self) -> None:
        self._cancelled = True


def get_runner(execution_id: int) -> "WorkflowRunner | None":
    return _runs.get(execution_id)


async def play_workflow(
    workflow_id: int,
    device_id: str,
    adb_address: str,
    steps: list[WorkflowStep],
    current_version: int,
    variables: dict | None = None,
    simulate: bool = False,
) -> WorkflowExecution:
    async with AsyncSessionLocal() as db:
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            workflow_version=current_version,
            device_id=device_id,
            adb_address=adb_address,
            variables_json=json.dumps(variables or {}),
            status="RUNNING",
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)

    runner = WorkflowRunner(execution, steps, variables or {}, simulate=simulate)
    _runs[execution.id] = runner
    asyncio.create_task(runner.run())
    return execution
