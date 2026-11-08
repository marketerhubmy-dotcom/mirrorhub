"""
Automation core: run an ordered list of steps on one or many phones.

* every step is validated up-front (type, ranges, package names, text) – a bad template is rejected
  before anything touches a phone;
* phones run in parallel, steps inside one phone run in order;
* per-step retries with delay, per-step timeout, ``continue_on_error``;
* cooperative + hard cancel (also interrupts ``wait``);
* one active run per device (starting a second is refused, never queued silently);
* all actuation goes through the validated ``adb_control`` / ``device_ops`` layer (no raw shell strings).

The ``Driver`` interface keeps the engine testable without a phone.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

from app.core import runtime_paths as rp
from app.services import adb_client, adb_control, device_ops

logger = logging.getLogger("mirrorhub.automation")

MAX_STEPS = 200
MAX_WAIT_S = 600
MAX_RETRIES = 5
MAX_RUNS_KEPT = 50
MAX_LOG_LINES = 500

# type → required fields
STEP_FIELDS: dict[str, tuple[str, ...]] = {
    "open_app": ("package",),
    "close_app": ("package",),
    "tap": ("x", "y"),
    "long_press": ("x", "y"),
    "swipe": ("x1", "y1", "x2", "y2"),
    "text": ("value",),
    "key": ("code",),
    "nav": ("action",),
    "wait": ("seconds",),
    "tap_text": ("text",),
    "wait_text": ("text",),
    "screenshot": (),
    "push_file": ("local", "remote"),
}
STEP_LABELS = {
    "open_app": "Buka aplikasi", "close_app": "Tutup aplikasi", "tap": "Ketik", "long_press": "Tekan lama",
    "swipe": "Leret", "text": "Taip teks", "key": "Tekan kekunci", "nav": "Navigasi", "wait": "Tunggu",
    "tap_text": "Ketik teks pada skrin", "wait_text": "Tunggu teks muncul", "screenshot": "Tangkap skrin",
    "push_file": "Hantar fail ke telefon",
}
_TEXT_MATCH_MAX = 200


class AutomationError(Exception):
    """A step failed (message is user-facing)."""


class StepValidationError(ValueError):
    pass


# ── validation ────────────────────────────────────────────────────────────────

def _num01(step: dict, key: str, idx: int) -> float:
    v = step.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= float(v) <= 1:
        raise StepValidationError(f"Langkah {idx + 1}: '{key}' mesti nombor antara 0 dan 1.")
    return float(v)


def validate_steps(steps: Any) -> list[dict]:
    if not isinstance(steps, list) or not steps:
        raise StepValidationError("Senarai langkah kosong.")
    if len(steps) > MAX_STEPS:
        raise StepValidationError(f"Terlalu banyak langkah (maks {MAX_STEPS}).")
    out: list[dict] = []
    for i, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise StepValidationError(f"Langkah {i + 1}: mesti objek.")
        t = raw.get("type")
        if t not in STEP_FIELDS:
            raise StepValidationError(f"Langkah {i + 1}: jenis '{t}' tidak dikenali.")
        for f in STEP_FIELDS[t]:
            if f not in raw:
                raise StepValidationError(f"Langkah {i + 1} ({t}): medan '{f}' diperlukan.")
        s: dict = {"type": t}
        try:
            if t in ("open_app", "close_app"):
                s["package"] = device_ops.validate_package(raw["package"])
            elif t in ("tap", "long_press"):
                s["x"], s["y"] = _num01(raw, "x", i), _num01(raw, "y", i)
            elif t == "swipe":
                for k in ("x1", "y1", "x2", "y2"):
                    s[k] = _num01(raw, k, i)
                ms = raw.get("ms", 300)
                if isinstance(ms, bool) or not isinstance(ms, int) or not 50 <= ms <= 5000:
                    raise StepValidationError(f"Langkah {i + 1}: 'ms' mesti 50–5000.")
                s["ms"] = ms
            elif t == "text":
                s["value"] = adb_control.validate_text(raw["value"])
            elif t == "key":
                s["code"] = adb_control.validate_keycode(raw["code"])
            elif t == "nav":
                if raw["action"] not in ("home", "back", "recents"):
                    raise StepValidationError(f"Langkah {i + 1}: nav mesti home/back/recents.")
                s["action"] = raw["action"]
            elif t == "wait":
                sec = raw["seconds"]
                if isinstance(sec, bool) or not isinstance(sec, (int, float)) or not 0 <= sec <= MAX_WAIT_S:
                    raise StepValidationError(f"Langkah {i + 1}: 'seconds' mesti 0–{MAX_WAIT_S}.")
                s["seconds"] = float(sec)
            elif t in ("tap_text", "wait_text"):
                txt = raw["text"]
                if not isinstance(txt, str) or not txt.strip() or len(txt) > _TEXT_MATCH_MAX:
                    raise StepValidationError(f"Langkah {i + 1}: 'text' tidak sah.")
                s["text"] = txt.strip()
                s["contains"] = bool(raw.get("contains", False))
                fb = raw.get("fallback")
                if fb is not None:
                    if t != "tap_text" or not (isinstance(fb, list) and len(fb) == 2):
                        raise StepValidationError(f"Langkah {i + 1}: 'fallback' mesti [x, y] (tap_text sahaja).")
                    s["fallback"] = [_num01({"v": fb[0]}, "v", i), _num01({"v": fb[1]}, "v", i)]
            elif t == "push_file":
                local = raw["local"]
                if not isinstance(local, str) or not Path(local).is_file():
                    raise StepValidationError(f"Langkah {i + 1}: fail tempatan tidak dijumpai.")
                s["local"] = local
                s["remote"] = device_ops.validate_remote_path(raw["remote"], allow_root=False)
        except (adb_control.ControlError, device_ops.OpError) as exc:
            raise StepValidationError(f"Langkah {i + 1} ({t}): {exc}") from exc

        retries = raw.get("retries", 0)
        if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= MAX_RETRIES:
            raise StepValidationError(f"Langkah {i + 1}: 'retries' mesti 0–{MAX_RETRIES}.")
        delay = raw.get("retry_delay", 1.0)
        if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= 60:
            raise StepValidationError(f"Langkah {i + 1}: 'retry_delay' mesti 0–60.")
        timeout = raw.get("timeout", 15 if t in ("tap_text", "wait_text") else 60)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600:
            raise StepValidationError(f"Langkah {i + 1}: 'timeout' mesti 1–600.")
        s.update(retries=retries, retry_delay=float(delay), timeout=float(timeout),
                 continue_on_error=bool(raw.get("continue_on_error", False)))
        label = raw.get("label")
        s["label"] = str(label)[:80] if label else STEP_LABELS[t]
        out.append(s)
    return out


# ── drivers ───────────────────────────────────────────────────────────────────

class Driver(Protocol):
    async def tap(self, x: float, y: float) -> None: ...
    async def long_press(self, x: float, y: float) -> None: ...
    async def swipe(self, x1: float, y1: float, x2: float, y2: float, ms: int) -> None: ...
    async def text(self, value: str) -> None: ...
    async def key(self, code: str) -> None: ...
    async def nav(self, action: str) -> None: ...
    async def open_app(self, package: str) -> None: ...
    async def close_app(self, package: str) -> None: ...
    async def find_text(self, text: str, contains: bool) -> tuple[int, int] | None: ...
    async def tap_px(self, x: int, y: int) -> None: ...
    async def screenshot(self, name: str) -> str: ...
    async def push(self, local: str, remote: str) -> None: ...


_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def find_in_hierarchy(xml_text: str, text: str, contains: bool = False) -> tuple[int, int] | None:
    """Centre of the first node whose text / content-desc matches (case-insensitive). Pure; unit-tested."""
    start = xml_text.find("<?xml")
    if start < 0:
        start = xml_text.find("<hierarchy")
    if start < 0:
        return None
    end = xml_text.rfind("</hierarchy>")
    body = xml_text[start:end + len("</hierarchy>")] if end >= 0 else xml_text[start:]
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    want = text.lower()
    for node in root.iter("node"):
        for attr in ("text", "content-desc"):
            val = (node.attrib.get(attr) or "").strip().lower()
            if val and (want in val if contains else val == want):
                m = _BOUNDS.match(node.attrib.get("bounds", ""))
                if m:
                    x1, y1, x2, y2 = map(int, m.groups())
                    if x2 > x1 and y2 > y1:
                        return (x1 + x2) // 2, (y1 + y2) // 2
    return None


class AdbDriver:
    def __init__(self, serial: str):
        self.serial = serial

    async def tap(self, x, y): await asyncio.to_thread(adb_control.tap, self.serial, x, y)
    async def long_press(self, x, y): await asyncio.to_thread(adb_control.long_press, self.serial, x, y)

    async def swipe(self, x1, y1, x2, y2, ms):
        if ms == 300:
            await asyncio.to_thread(adb_control.swipe, self.serial, x1, y1, x2, y2)
        else:
            w, h = await asyncio.to_thread(adb_control.get_screen_size, self.serial)
            px = lambda r, n: int(r * (n - 1))
            await asyncio.to_thread(adb_control._send, self.serial,
                                    f"input swipe {px(x1, w)} {px(y1, h)} {px(x2, w)} {px(y2, h)} {int(ms)}")

    async def text(self, value): await asyncio.to_thread(adb_control.input_text, self.serial, value)
    async def key(self, code): await asyncio.to_thread(adb_control.keyevent, self.serial, code)
    async def nav(self, action): await asyncio.to_thread(adb_control.nav, self.serial, action)
    async def tap_px(self, x, y): await asyncio.to_thread(adb_control.tap_px, self.serial, x, y)

    async def open_app(self, package):
        ok, msg = await device_ops.launch(self.serial, package)
        if not ok:
            raise AutomationError(f"{package}: {msg}")

    async def close_app(self, package):
        ok, msg = await device_ops.force_stop(self.serial, package)
        if not ok:
            raise AutomationError(f"{package}: {msg}")

    async def find_text(self, text, contains):
        rc, out, err = await adb_client.run_adb_bytes("exec-out", "uiautomator", "dump", "/dev/tty",
                                                      serial=self.serial, timeout=20)
        if rc != 0 and not out:
            raise AutomationError(err or "uiautomator dump gagal")
        return find_in_hierarchy(out.decode("utf-8", "replace"), text, contains)

    async def screenshot(self, name):
        png = await device_ops.screenshot(self.serial)
        d = rp.data_dir() / "screenshots"
        d.mkdir(exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:60] or "shot"
        p = d / f"{safe}_{int(time.time())}.png"
        p.write_bytes(png)
        return str(p)

    async def push(self, local, remote):
        p = Path(remote)
        await device_ops.push_file(self.serial, Path(local), str(p.parent).replace("\\", "/"), p.name)


# ── execution ─────────────────────────────────────────────────────────────────

@dataclass
class DeviceRun:
    device_id: str
    serial: str
    name: str
    state: str = "queued"           # queued | running | succeeded | failed | cancelled
    step_index: int = -1
    steps_done: int = 0
    error: str = ""
    logs: list[dict] = field(default_factory=list)
    started_at: float | None = None
    finished_at: float | None = None

    def log(self, level: str, msg: str) -> None:
        if len(self.logs) >= MAX_LOG_LINES:
            self.logs.pop(0)
        self.logs.append({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": level, "msg": msg})

    def to_dict(self, with_logs: bool = True) -> dict:
        d = {"device_id": self.device_id, "name": self.name, "state": self.state, "step_index": self.step_index,
             "steps_done": self.steps_done, "error": self.error, "started_at": self.started_at,
             "finished_at": self.finished_at}
        if with_logs:
            d["logs"] = self.logs
        return d


@dataclass
class Run:
    id: str
    name: str
    steps: list[dict]
    devices: dict[str, DeviceRun]
    created_at: float = field(default_factory=time.time)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task] = field(default_factory=list)

    @property
    def state(self) -> str:
        sts = {d.state for d in self.devices.values()}
        if sts & {"queued", "running"}:
            return "running"
        if "failed" in sts:
            return "failed"
        if "cancelled" in sts:
            return "cancelled"
        return "succeeded"

    def to_dict(self, with_logs: bool = False) -> dict:
        return {"id": self.id, "name": self.name, "state": self.state, "created_at": self.created_at,
                "total_steps": len(self.steps), "steps": [{"type": s["type"], "label": s["label"]} for s in self.steps],
                "devices": [d.to_dict(with_logs) for d in self.devices.values()]}


class AutomationEngine:
    def __init__(self, driver_factory: Callable[[str], Driver] | None = None):
        self._driver_factory = driver_factory or AdbDriver
        self.runs: dict[str, Run] = {}
        self._busy: dict[str, str] = {}      # device_id -> run id

    # ── public API ───────────────────────────────────────────────────────────
    def busy_devices(self, device_ids: list[str]) -> list[str]:
        return [d for d in device_ids if d in self._busy]

    def start(self, name: str, steps: list[dict], devices: list[tuple[str, str, str]]) -> Run:
        """devices: (device_id, adb serial, display name). Steps must already be validated."""
        if not devices:
            raise StepValidationError("Pilih sekurang-kurangnya satu peranti.")
        clash = self.busy_devices([d[0] for d in devices])
        if clash:
            raise StepValidationError(f"Peranti sedang menjalankan automasi lain: {', '.join(clash)}")
        run = Run(id=uuid.uuid4().hex[:12], name=(name or "Automasi")[:80], steps=steps,
                  devices={d[0]: DeviceRun(d[0], d[1], d[2]) for d in devices})
        self.runs[run.id] = run
        self._prune()
        for dr in run.devices.values():
            self._busy[dr.device_id] = run.id
            run.tasks.append(asyncio.create_task(self._run_device(run, dr), name=f"auto-{run.id}-{dr.device_id}"))
        return run

    def cancel(self, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if not run or run.state != "running":
            return False
        run.cancel_event.set()
        return True

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def list(self) -> list[Run]:
        return sorted(self.runs.values(), key=lambda r: r.created_at, reverse=True)

    async def shutdown(self) -> None:
        for r in self.runs.values():
            r.cancel_event.set()
        tasks = [t for r in self.runs.values() for t in r.tasks if not t.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=5)
            for t in tasks:
                t.cancel()

    # ── internals ────────────────────────────────────────────────────────────
    def _prune(self) -> None:
        finished = [r for r in self.list() if r.state != "running"]
        for r in finished[MAX_RUNS_KEPT:]:
            self.runs.pop(r.id, None)

    async def _interruptible(self, run: Run, coro: Awaitable, timeout: float) -> Any:
        """Await coro unless the run is cancelled (→ CancelledError-like AutomationError) or timeout elapses."""
        task = asyncio.ensure_future(coro)
        cancel = asyncio.ensure_future(run.cancel_event.wait())
        try:
            done, _ = await asyncio.wait({task, cancel}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                return task.result()
            if cancel in done:
                raise _Cancelled()
            raise AutomationError(f"tamat masa ({timeout:.0f}s)")
        finally:
            for t in (task, cancel):
                if not t.done():
                    t.cancel()
            await asyncio.gather(task, cancel, return_exceptions=True)

    async def _run_device(self, run: Run, dr: DeviceRun) -> None:
        dr.state = "running"
        dr.started_at = time.time()
        driver = self._driver_factory(dr.serial)
        try:
            for i, step in enumerate(run.steps):
                if run.cancel_event.is_set():
                    raise _Cancelled()
                dr.step_index = i
                dr.log("info", f"[{i + 1}/{len(run.steps)}] {step['label']}")
                attempts = step["retries"] + 1
                for attempt in range(1, attempts + 1):
                    try:
                        await self._interruptible(run, self._do_step(driver, step), step["timeout"] if step["type"] != "wait" else step["seconds"] + 5)
                        break
                    except _Cancelled:
                        raise
                    except Exception as exc:
                        msg = str(exc) or exc.__class__.__name__
                        if attempt < attempts:
                            dr.log("warn", f"  gagal (cuba {attempt}/{attempts}): {msg}")
                            await self._interruptible(run, asyncio.sleep(step["retry_delay"]), step["retry_delay"] + 5)
                            continue
                        if step["continue_on_error"]:
                            dr.log("warn", f"  gagal tetapi diteruskan: {msg}")
                            break
                        raise AutomationError(f"Langkah {i + 1} ({step['label']}): {msg}") from exc
                dr.steps_done = i + 1
            dr.state = "succeeded"
            dr.log("ok", "Selesai.")
        except _Cancelled:
            dr.state = "cancelled"
            dr.log("warn", "Dibatalkan.")
        except Exception as exc:
            dr.state = "failed"
            dr.error = str(exc)
            dr.log("error", dr.error)
            logger.warning("automation %s device %s failed: %s", run.id, dr.device_id, exc)
        finally:
            dr.finished_at = time.time()
            self._busy.pop(dr.device_id, None)

    async def _do_step(self, d: Driver, s: dict) -> None:
        t = s["type"]
        if t == "tap": await d.tap(s["x"], s["y"])
        elif t == "long_press": await d.long_press(s["x"], s["y"])
        elif t == "swipe": await d.swipe(s["x1"], s["y1"], s["x2"], s["y2"], s["ms"])
        elif t == "text": await d.text(s["value"])
        elif t == "key": await d.key(s["code"])
        elif t == "nav": await d.nav(s["action"])
        elif t == "open_app": await d.open_app(s["package"])
        elif t == "close_app": await d.close_app(s["package"])
        elif t == "wait": await asyncio.sleep(s["seconds"])
        elif t == "tap_text":
            pos = await d.find_text(s["text"], s["contains"])
            if pos is not None:
                await d.tap_px(*pos)
            elif s.get("fallback"):
                await d.tap(*s["fallback"])
            else:
                raise AutomationError(f"teks '{s['text']}' tidak dijumpai pada skrin")
        elif t == "wait_text":
            end = time.monotonic() + s["timeout"] - 1
            while True:
                if await d.find_text(s["text"], s["contains"]) is not None:
                    return
                if time.monotonic() >= end:
                    raise AutomationError(f"teks '{s['text']}' tidak muncul")
                await asyncio.sleep(1.0)
        elif t == "screenshot": await d.screenshot(s["label"])
        elif t == "push_file": await d.push(s["local"], s["remote"])
        else:  # unreachable: validate_steps rejects unknown types
            raise AutomationError(f"jenis langkah tidak disokong: {t}")


class _Cancelled(Exception):
    pass


_engine: AutomationEngine | None = None


def get_engine() -> AutomationEngine:
    global _engine
    if _engine is None:
        _engine = AutomationEngine()
    return _engine
