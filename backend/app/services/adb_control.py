"""Low-latency input control over a persistent ``adb shell`` per device.

Security notes (see docs/AUDIT.md S1/S3, docs/DECISIONS.md ADR-003):
- Everything typed into the persistent shell is a shell command line, so every
  user-influenced value is either numeric-validated or POSIX single-quoted.
- Newlines / control characters are rejected outright (they would terminate the
  command line and start a new one).
- Errors are raised as ``ControlError`` instead of being swallowed.
"""
from __future__ import annotations

import logging
import math
import re
import subprocess
import threading

from app.utils.adb_path import ADB

logger = logging.getLogger("mirrorhub.control")

MAX_TEXT_LEN = 500
_SERIAL_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")
_KEYCODE_NAME_RE = re.compile(r"^KEYCODE_[A-Z0-9_]{1,48}$")
_NAV_KEYS = {"home": "KEYCODE_HOME", "back": "KEYCODE_BACK", "recents": "KEYCODE_APP_SWITCH"}

_size_cache: dict[str, tuple[int, int]] = {}
_shells: dict[str, subprocess.Popen] = {}
_shell_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


class ControlError(ValueError):
    """Invalid or undeliverable control command."""


# ── validation / quoting ──────────────────────────────────────────────────────

def validate_serial(adb_address: str) -> str:
    if not isinstance(adb_address, str) or not _SERIAL_RE.match(adb_address):
        raise ControlError("invalid device address")
    return adb_address


def sh_quote(value: str) -> str:
    """POSIX single-quote a string so the device shell treats it literally."""
    return "'" + value.replace("'", "'\\''") + "'"


def validate_rel(value: object, name: str = "coordinate") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ControlError(f"{name} must be a number")
    v = float(value)
    if not math.isfinite(v) or v < 0.0 or v > 1.0:
        raise ControlError(f"{name} must be within 0..1")
    return v


def validate_text(text: object) -> str:
    if not isinstance(text, str):
        raise ControlError("text must be a string")
    if len(text) > MAX_TEXT_LEN:
        raise ControlError(f"text too long (max {MAX_TEXT_LEN})")
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ControlError("text contains control characters")
    return text


def validate_keycode(code: object) -> str:
    if isinstance(code, bool):
        raise ControlError("invalid keycode")
    if isinstance(code, int):
        if 0 <= code <= 400:
            return str(code)
        raise ControlError("keycode out of range")
    if isinstance(code, str):
        if code.isdigit() and 0 <= int(code) <= 400:
            return str(int(code))
        if _KEYCODE_NAME_RE.match(code):
            return code
    raise ControlError("invalid keycode")


# ── persistent shell ──────────────────────────────────────────────────────────

def _lock_for(adb_address: str) -> threading.Lock:
    with _registry_lock:
        lock = _shell_locks.get(adb_address)
        if lock is None:
            lock = _shell_locks[adb_address] = threading.Lock()
        return lock


def _get_shell(adb_address: str) -> subprocess.Popen:
    """Keep one persistent adb shell per device (caller must hold its lock)."""
    shell = _shells.get(adb_address)
    if shell is None or shell.poll() is not None:
        shell = subprocess.Popen(
            [str(ADB), "-s", adb_address, "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        _shells[adb_address] = shell
    return shell


def _send(adb_address: str, cmd: str) -> None:
    validate_serial(adb_address)
    if "\n" in cmd or "\r" in cmd:  # defence in depth
        raise ControlError("command contains a newline")
    with _lock_for(adb_address):
        try:
            shell = _get_shell(adb_address)
            shell.stdin.write(f"{cmd}\n".encode("utf-8"))
            shell.stdin.flush()
        except Exception as exc:
            _shells.pop(adb_address, None)
            logger.warning("control send failed device=%s: %s", adb_address, exc)
            raise ControlError(f"device shell unavailable: {exc}") from exc


def close_shell(adb_address: str) -> None:
    with _lock_for(adb_address):
        shell = _shells.pop(adb_address, None)
    if shell and shell.poll() is None:
        shell.terminate()


def get_screen_size(adb_address: str) -> tuple[int, int]:
    validate_serial(adb_address)
    if adb_address in _size_cache:
        return _size_cache[adb_address]
    try:
        result = subprocess.run(
            [str(ADB), "-s", adb_address, "shell", "wm", "size"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        size_str = result.stdout.strip().split(":")[-1].strip()
        w, h = size_str.split("x")
        size = (int(w), int(h))
    except Exception:
        # Do not cache a guess: let the next call retry.
        return (1080, 2400)
    _size_cache[adb_address] = size
    return size


def _px(adb_address: str, rx: float, ry: float) -> tuple[int, int]:
    w, h = get_screen_size(adb_address)
    return int(validate_rel(rx, "x") * (w - 1)), int(validate_rel(ry, "y") * (h - 1))


# ── commands ──────────────────────────────────────────────────────────────────

def tap(adb_address: str, rx: float, ry: float) -> None:
    x, y = _px(adb_address, rx, ry)
    _send(adb_address, f"input tap {x} {y}")


def tap_px(adb_address: str, x: int, y: int) -> None:
    """Tap at ABSOLUTE pixels (used by UI-text matching). Integers only, bounded."""
    for v in (x, y):
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 20000:
            raise ControlError("pixel coordinate must be an integer 0..20000")
    _send(adb_address, f"input tap {x} {y}")


def long_press(adb_address: str, rx: float, ry: float) -> None:
    x, y = _px(adb_address, rx, ry)
    _send(adb_address, f"input swipe {x} {y} {x} {y} 700")


def swipe(adb_address: str, rx1: float, ry1: float, rx2: float, ry2: float) -> None:
    x1, y1 = _px(adb_address, rx1, ry1)
    x2, y2 = _px(adb_address, rx2, ry2)
    _send(adb_address, f"input swipe {x1} {y1} {x2} {y2} 300")


def input_text(adb_address: str, text: str) -> None:
    text = validate_text(text)
    if not text:
        return
    # `input text` encodes a space as %s; quote the whole argument for sh.
    _send(adb_address, f"input text {sh_quote(text.replace(' ', '%s'))}")


def keyevent(adb_address: str, code: object) -> None:
    _send(adb_address, f"input keyevent {validate_keycode(code)}")


def nav(adb_address: str, action: str) -> None:
    code = _NAV_KEYS.get(action) if isinstance(action, str) else None
    if code is None:
        raise ControlError(f"unknown nav action: {action!r}")
    keyevent(adb_address, code)
