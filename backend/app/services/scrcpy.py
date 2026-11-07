import asyncio
import subprocess

from app.utils.adb_path import ADB, SCRCPY

_lock = asyncio.Lock()
_active: dict[str, subprocess.Popen] = {}


async def adb_connect(adb_address: str) -> tuple[bool, str]:
    """Connect ADB to a device address. Non-blocking — runs subprocess in thread."""
    result = await asyncio.to_thread(
        subprocess.run,
        [str(ADB), "connect", adb_address],
        capture_output=True, text=True, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    output = result.stdout + result.stderr
    success = "connected" in output.lower() or "already connected" in output.lower()
    return success, output.strip()


async def start_mirror(device_id: str, adb_address: str, device_name: str = "") -> tuple[bool, str]:
    """Launch scrcpy for a device. Fully async — never blocks the event loop."""
    title = device_name or device_id
    async with _lock:
        if device_id in _active:
            proc = _active[device_id]
            if proc.poll() is None:
                return True, "Already running"

        try:
            conn_result = await asyncio.to_thread(
                subprocess.run,
                [str(ADB), "connect", adb_address],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            conn_out = conn_result.stdout + conn_result.stderr
        except subprocess.TimeoutExpired:
            conn_out = "timeout"
        if "connected to" not in conn_out.lower():
            return (
                False,
                f"ADB tidak dapat connect ke {adb_address}. "
                "Pastikan phone dan laptop dalam WiFi sama dan Wireless Debugging ON. "
                "Port Wireless Debugging berubah setiap kali ia dihidupkan semula — "
                "kalau port lama, sambung semula dengan port baharu.",
            )

        try:
            proc = subprocess.Popen(
                [
                    str(SCRCPY),
                    "-s", adb_address,
                    "--video-codec=h264",
                    "--audio-codec=opus",
                    "--max-size=1080",
                    "--max-fps=30",
                    f"--window-title=\U0001f4f1 {title}",
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            # Non-blocking wait to detect immediate crash (e.g. device not found)
            await asyncio.sleep(1.5)
            if proc.poll() is not None:
                return False, "scrcpy keluar awal. Pastikan phone connected dan Wireless Debugging ON."
            _active[device_id] = proc
            return True, f"Mirror started (pid={proc.pid})"
        except Exception as e:
            return False, str(e)


async def stop_mirror(device_id: str) -> bool:
    async with _lock:
        proc = _active.pop(device_id, None)
        if proc and proc.poll() is None:
            proc.terminate()
            return True
        return False


def is_mirroring(device_id: str) -> bool:
    proc = _active.get(device_id)
    return proc is not None and proc.poll() is None


def active_mirrors() -> list[str]:
    return [did for did, p in _active.items() if p.poll() is None]
