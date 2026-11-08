"""
Whole-PC metrics (CPU %, RAM) without extra dependencies (ctypes on Windows).

Kept separate from ``metrics.process_metrics`` (this process only) so the dashboard can show both honestly.
Returns ``None`` for anything it cannot measure; callers display N/A rather than inventing a number.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass


@dataclass
class SystemSample:
    cpu_pct: float | None
    ram_used_mb: float | None
    ram_total_mb: float | None
    ram_pct: float | None
    cpu_count: int


def _ft(ft) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


class SystemMonitor:
    """Stateful: CPU % is computed from the delta between two calls to ``sample()``."""

    def __init__(self) -> None:
        self._last: tuple[int, int, int] | None = None   # idle, kernel, user
        self.available = sys.platform == "win32"

    # ── windows primitives (replaceable in tests); ctypes types are created once, not per call ──
    _W: dict = {}

    @classmethod
    def _win(cls) -> dict:
        if cls._W:
            return cls._W
        import ctypes
        from ctypes import wintypes

        class MSX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3
        k32.GetSystemTimes.restype = wintypes.BOOL
        k32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MSX)]
        k32.GlobalMemoryStatusEx.restype = wintypes.BOOL
        cls._W.update(ctypes=ctypes, wintypes=wintypes, MSX=MSX, k32=k32)
        return cls._W

    def _times(self) -> tuple[int, int, int] | None:
        w = self._win()
        ctypes, wintypes = w["ctypes"], w["wintypes"]
        idle, kern, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        if not w["k32"].GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
            return None
        return _ft(idle), _ft(kern), _ft(user)

    def _memory(self) -> tuple[float, float] | None:
        w = self._win()
        m = w["MSX"]()
        m.dwLength = w["ctypes"].sizeof(w["MSX"])
        if not w["k32"].GlobalMemoryStatusEx(w["ctypes"].byref(m)):
            return None
        total = m.ullTotalPhys / 1048576
        return total - m.ullAvailPhys / 1048576, total

    def sample(self) -> SystemSample:
        cpu = None
        used = total = pct = None
        if self.available:
            try:
                cur = self._times()
                if cur and self._last:
                    d_idle, d_kern, d_user = (cur[i] - self._last[i] for i in range(3))
                    busy_total = d_kern + d_user            # kernel time includes idle time
                    if busy_total > 0:
                        cpu = max(0.0, min(100.0, 100.0 * (busy_total - d_idle) / busy_total))
                if cur:
                    self._last = cur
            except Exception:
                cpu = None
            try:
                mem = self._memory()
                if mem:
                    used, total = mem
                    pct = 100.0 * used / total if total else None
            except Exception:
                used = total = pct = None
        return SystemSample(
            cpu_pct=None if cpu is None else round(cpu, 1),
            ram_used_mb=None if used is None else round(used, 0),
            ram_total_mb=None if total is None else round(total, 0),
            ram_pct=None if pct is None else round(pct, 1),
            cpu_count=os.cpu_count() or 1,
        )


class ProcessCpu:
    """This process' CPU %, normalised to 0..100 over all logical CPUs."""

    def __init__(self) -> None:
        self._cpu = time.process_time()
        self._wall = time.monotonic()
        self._n = os.cpu_count() or 1

    def sample(self) -> float:
        cpu, wall = time.process_time(), time.monotonic()
        dc, dw = cpu - self._cpu, wall - self._wall
        self._cpu, self._wall = cpu, wall
        if dw <= 0:
            return 0.0
        return round(max(0.0, min(100.0, 100.0 * dc / dw / self._n)), 2)
