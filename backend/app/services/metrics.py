"""Process metrics without extra dependencies (ctypes on Windows) – used by /api/v1/system/metrics and the soak tool."""
from __future__ import annotations

import os
import sys
import threading
import time

_START = time.time()


def _win_process_info() -> dict:
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    k32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetProcessHandleCount.restype = wintypes.BOOL
    h = k32.GetCurrentProcess()
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    ok = psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    handles = wintypes.DWORD(0)
    k32.GetProcessHandleCount(h, ctypes.byref(handles))
    return {"rss_mb": round(pmc.WorkingSetSize / 1048576, 1) if ok else None, "handles": handles.value}


def process_metrics() -> dict:
    info = {"rss_mb": None, "handles": None}
    if sys.platform == "win32":
        try:
            info = _win_process_info()
        except Exception:
            pass
    return {
        "pid": os.getpid(),
        "uptime_s": round(time.time() - _START),
        "cpu_time_s": round(time.process_time(), 2),
        "threads": threading.active_count(),
        **info,
    }
