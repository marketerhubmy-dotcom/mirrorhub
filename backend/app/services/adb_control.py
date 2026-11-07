import subprocess
import threading

from app.utils.adb_path import ADB

_size_cache: dict[str, tuple[int, int]] = {}
_shells: dict[str, subprocess.Popen] = {}
_shell_locks: dict[str, threading.Lock] = {}


def _get_shell(adb_address: str) -> subprocess.Popen:
    """Keep one persistent adb shell per device — much faster than spawning each time."""
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
        _shell_locks[adb_address] = threading.Lock()
    return shell


def _send(adb_address: str, cmd: str) -> None:
    lock = _shell_locks.get(adb_address) or threading.Lock()
    with lock:
        try:
            shell = _get_shell(adb_address)
            shell.stdin.write(f"{cmd}\n".encode())
            shell.stdin.flush()
        except Exception:
            _shells.pop(adb_address, None)


def get_screen_size(adb_address: str) -> tuple[int, int]:
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
        size = (1080, 2400)
    _size_cache[adb_address] = size
    return size


def _px(adb_address: str, rx: float, ry: float) -> tuple[int, int]:
    w, h = get_screen_size(adb_address)
    return int(rx * w), int(ry * h)


def tap(adb_address: str, rx: float, ry: float) -> None:
    x, y = _px(adb_address, rx, ry)
    _send(adb_address, f"input tap {x} {y}")


def long_press(adb_address: str, rx: float, ry: float) -> None:
    x, y = _px(adb_address, rx, ry)
    _send(adb_address, f"input swipe {x} {y} {x} {y} 700")


def swipe(adb_address: str, rx1: float, ry1: float, rx2: float, ry2: float) -> None:
    w, h = get_screen_size(adb_address)
    x1, y1 = int(rx1 * w), int(ry1 * h)
    x2, y2 = int(rx2 * w), int(ry2 * h)
    _send(adb_address, f"input swipe {x1} {y1} {x2} {y2} 300")


def input_text(adb_address: str, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace(" ", "%s").replace("'", "\\'")
    _send(adb_address, f"input text '{escaped}'")


def keyevent(adb_address: str, code: str) -> None:
    _send(adb_address, f"input keyevent {code}")


def nav(adb_address: str, action: str) -> None:
    keycodes = {"home": "KEYCODE_HOME", "back": "KEYCODE_BACK", "recents": "KEYCODE_APP_SWITCH"}
    code = keycodes.get(action)
    if code:
        keyevent(adb_address, code)
