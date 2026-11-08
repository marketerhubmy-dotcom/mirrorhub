"""
Device health checking.

Probes a device via ADB (non-blocking) and returns a HealthSnapshot.
The monitor calls this on a per-device basis every HEALTH_POLL_INTERVAL seconds.
"""
import asyncio
import subprocess
import time
from dataclasses import dataclass

from app.services import adb_client
from app.utils.adb_path import ADB  # noqa: F401  (kept for modules that patch it)


@dataclass
class HealthSnapshot:
    device_id: str
    adb_address: str
    reachable: bool
    latency_ms: float               # ADB round-trip time
    battery_pct: int
    android_version: str
    resolution_w: int
    resolution_h: int
    ram_mb: int
    storage_gb: float
    performance_score: float        # 0.0–10.0 computed score


def _compute_score(
    battery_pct: int,
    latency_ms: float,
    success_rate: float,  # 0.0–1.0
) -> float:
    """
    Compute a 0–10 performance score.

    Higher battery, lower latency, and higher success rate = higher score.
    """
    if not battery_pct and not latency_ms:
        return 5.0  # unknown — neutral

    battery_score = battery_pct / 100.0 * 3.0          # up to 3 pts
    latency_score = max(0, 3.0 - latency_ms / 200.0)    # up to 3 pts (0 = 600ms+)
    success_score = success_rate * 4.0                  # up to 4 pts

    return min(10.0, round(battery_score + latency_score + success_score, 2))


async def check_device(device_id: str, adb_address: str) -> HealthSnapshot:
    """
    Probe a device. Returns a HealthSnapshot.

    Uses a lightweight `adb shell echo ok` ping to measure latency.
    All capability queries are best-effort — failures return defaults.
    """
    # ── Latency ping ─────────────────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        # thread-based runner: asyncio subprocesses leave pipe-transport reference cycles (see adb_client.run_adb)
        r = await adb_client.run_adb("shell", "echo", "ok", serial=adb_address, timeout=5.0)
        reachable = r.rc == 0 and "ok" in r.out
    except (asyncio.TimeoutError, Exception):
        reachable = False

    latency_ms = (time.monotonic() - t0) * 1000 if reachable else 0.0

    if not reachable:
        return HealthSnapshot(
            device_id=device_id,
            adb_address=adb_address,
            reachable=False,
            latency_ms=0.0,
            battery_pct=0,
            android_version="",
            resolution_w=0,
            resolution_h=0,
            ram_mb=0,
            storage_gb=0.0,
            performance_score=0.0,
        )

    # ── Battery ──────────────────────────────────────────────────────────────
    battery_pct = await _adb_int(adb_address, "shell dumpsys battery | grep level")

    # ── Android version ──────────────────────────────────────────────────────
    android_version = await _adb_str(
        adb_address, "shell getprop ro.build.version.release"
    )

    # ── Resolution ───────────────────────────────────────────────────────────
    res_str = await _adb_str(adb_address, "shell wm size")
    resolution_w, resolution_h = _parse_resolution(res_str)

    # ── RAM ──────────────────────────────────────────────────────────────────
    ram_mb = await _adb_ram(adb_address)

    # ── Storage ──────────────────────────────────────────────────────────────
    storage_gb = await _adb_storage(adb_address)

    score = _compute_score(battery_pct, latency_ms, 1.0)

    return HealthSnapshot(
        device_id=device_id,
        adb_address=adb_address,
        reachable=True,
        latency_ms=round(latency_ms, 1),
        battery_pct=battery_pct,
        android_version=android_version.strip(),
        resolution_w=resolution_w,
        resolution_h=resolution_h,
        ram_mb=ram_mb,
        storage_gb=storage_gb,
        performance_score=score,
    )


# ── ADB helpers ───────────────────────────────────────────────────────────────

async def _adb_run(adb_address: str, shell_cmd: str) -> str:
    """Run a shell command, return stdout as string. Empty string on failure."""
    try:
        parts = ["shell"] + shell_cmd.split(None, 1)[1:] if shell_cmd.startswith("shell ") else shell_cmd.split()
        r = await adb_client.run_adb(*parts, serial=adb_address, timeout=5.0)
        return r.out.strip()
    except Exception:
        return ""


async def _adb_int(adb_address: str, cmd: str) -> int:
    out = await _adb_run(adb_address, cmd)
    for part in out.split():
        try:
            return int(part)
        except ValueError:
            continue
    return 0


async def _adb_str(adb_address: str, cmd: str) -> str:
    return await _adb_run(adb_address, cmd)


def _parse_resolution(res_str: str) -> tuple[int, int]:
    try:
        clean = res_str.split(":")[-1].strip()
        w, h = clean.split("x")
        return int(w), int(h)
    except Exception:
        return 1080, 2400


async def _adb_ram(adb_address: str) -> int:
    out = await _adb_run(adb_address, "shell cat /proc/meminfo")
    for line in out.splitlines():
        if "MemTotal" in line:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1]) // 1024  # kB → MB
                except ValueError:
                    pass
    return 0


async def _adb_storage(adb_address: str) -> float:
    out = await _adb_run(adb_address, "shell df /sdcard")
    for line in out.splitlines():
        if "/sdcard" in line or "fuse" in line.lower():
            parts = line.split()
            if len(parts) >= 2:
                try:
                    total_kb = int(parts[1].replace("K", ""))
                    return round(total_kb / 1024 / 1024, 1)
                except (ValueError, IndexError):
                    pass
    return 0.0
