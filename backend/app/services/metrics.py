"""Process metrics without extra dependencies (ctypes on Windows) – used by /api/v1/system/metrics and the soak tool."""
from __future__ import annotations

import os
import sys
import threading
import time

_START = time.time()


_WIN: dict = {}


def _win_init() -> dict:
    """Define the ctypes structure and bind the DLL functions ONCE (a new Structure class per call is a reference
    cycle the collector must free later — it showed up as steady memory growth in the idle backend)."""
    if _WIN:
        return _WIN
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
    _WIN.update(ctypes=ctypes, wintypes=wintypes, PMC=PMC, k32=k32, psapi=psapi, handle=k32.GetCurrentProcess())
    return _WIN


def _win_process_info() -> dict:
    w = _win_init()
    ctypes, wintypes, PMC = w["ctypes"], w["wintypes"], w["PMC"]
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    ok = w["psapi"].GetProcessMemoryInfo(w["handle"], ctypes.byref(pmc), pmc.cb)
    handles = wintypes.DWORD(0)
    w["k32"].GetProcessHandleCount(w["handle"], ctypes.byref(handles))
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
