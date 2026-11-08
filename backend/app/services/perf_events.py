"""
Bounded, in-memory event log for stream/device lifecycle, errors and alerts.

``emit`` is safe to call from anywhere (sync, never raises, never blocks); retention is capped so the log
itself cannot grow without limit.  Used by the Performance dashboard and the diagnostic report.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

MAX_EVENTS = 1000

_lock = threading.Lock()
_events: deque[dict] = deque(maxlen=MAX_EVENTS)
_seq = 0
_listeners: list[Callable[[dict], None]] = []
_counters: dict[str, int] = {}

KINDS = ("stream", "device", "adb", "alert", "error", "system")


def emit(kind: str, message: str, *, device_id: str | None = None, level: str = "info", **data) -> dict:
    global _seq
    ev = {"t": time.time(), "kind": kind if kind in KINDS else "system", "level": level,
          "device_id": device_id, "message": str(message)[:300], "data": {k: v for k, v in data.items() if v is not None}}
    with _lock:
        _seq += 1
        ev["id"] = _seq
        _events.append(ev)
        key = f"{ev['kind']}:{level}"
        _counters[key] = _counters.get(key, 0) + 1
        listeners = list(_listeners)
    for cb in listeners:
        try:
            cb(ev)
        except Exception:  # a broken listener must never break the emitter
            pass
    return ev


def recent(limit: int = 200, *, device_id: str | None = None, kind: str | None = None, since_id: int = 0) -> list[dict]:
    with _lock:
        items = [e for e in _events if e["id"] > since_id]
    if device_id:
        items = [e for e in items if e["device_id"] == device_id]
    if kind:
        items = [e for e in items if e["kind"] == kind]
    return items[-limit:]


def count_since(kind: str, since_ts: float, *, device_id: str | None = None, match: str | None = None) -> int:
    with _lock:
        return sum(1 for e in _events if e["kind"] == kind and e["t"] >= since_ts
                   and (device_id is None or e["device_id"] == device_id)
                   and (match is None or match in e["message"] or match == e["data"].get("event")))


def subscribe(cb: Callable[[dict], None]) -> None:
    with _lock:
        if cb not in _listeners:
            _listeners.append(cb)


def unsubscribe(cb: Callable[[dict], None]) -> None:
    with _lock:
        if cb in _listeners:
            _listeners.remove(cb)


def reset() -> None:
    """Tests only."""
    global _seq
    with _lock:
        _events.clear()
        _counters.clear()
        _seq = 0
