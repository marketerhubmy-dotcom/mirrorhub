"""
Persistent user preferences (``%APPDATA%\\Mirrorhub\\preferences.json``).

Server-side on purpose: the desktop window's browser storage can be wiped or differ per origin, while this file
survives restarts, updates and port changes.  Writes are atomic; a corrupt file is moved aside (never deleted)
and defaults are used.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable

from app.core import runtime_paths as rp

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# key -> (default, validator)  – validator returns the normalised value or raises ValueError
def _choice(*opts):
    def v(x):
        if x not in opts:
            raise ValueError(f"mesti salah satu daripada {list(opts)}")
        return x
    return v


def _bool(x):
    if not isinstance(x, bool):
        raise ValueError("mesti true/false")
    return x


def _int(lo, hi):
    def v(x):
        if isinstance(x, bool) or not isinstance(x, int) or not lo <= x <= hi:
            raise ValueError(f"mesti integer {lo}-{hi}")
        return x
    return v


SCHEMA: dict[str, tuple[Any, Callable[[Any], Any]]] = {
    "wall_layout": ("auto", _choice("auto", 1, 2, 4, 9)),
    "wall_show_offline": (False, _bool),
    "wall_quality": ("auto", _choice("auto", "thumb", "normal", "focus")),
    "auto_reconnect": (True, _bool),
    "record_seconds": (60, _int(5, 180)),
}
DEFAULTS = {k: d for k, (d, _) in SCHEMA.items()}


def _path():
    return rp.data_dir() / "preferences.json"


def load() -> dict:
    with _lock:
        prefs = dict(DEFAULTS)
        p = _path()
        if not p.exists():
            return prefs
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as exc:
            aside = p.with_name(f"preferences.corrupt.{int(time.time())}.json")
            try:
                p.replace(aside)
            except OSError:
                pass
            logger.warning("preferences.json unreadable (%s); moved to %s, using defaults", exc, aside.name)
            return prefs
        for k, (d, validate) in SCHEMA.items():
            if k in raw:
                try:
                    prefs[k] = validate(raw[k])
                except ValueError:
                    pass          # ignore a bad single value, keep the rest
        return prefs


def update(patch: dict) -> dict:
    """Validate and persist a partial update. Unknown keys and invalid values raise ValueError (nothing is written)."""
    if not isinstance(patch, dict) or not patch:
        raise ValueError("tiada perubahan")
    clean = {}
    for k, v in patch.items():
        if k not in SCHEMA:
            raise ValueError(f"tetapan tidak dikenali: {k}")
        try:
            clean[k] = SCHEMA[k][1](v)
        except ValueError as exc:
            raise ValueError(f"{k}: {exc}") from exc
    cur = load()
    cur.update(clean)
    with _lock:
        p = _path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    return cur


def get(key: str):
    return load().get(key, DEFAULTS[key])
