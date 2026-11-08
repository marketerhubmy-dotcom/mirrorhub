"""
Environment diagnostics shared by the Settings page, /api/v1/system/diagnostics
and the command-line tool (``python -m app.tools.diag``).

Each check returns {id, title, status: PASS|WARN|FAIL|INFO, detail, hint}.
These verify the *environment*; they never claim a phone works unless one was
actually exercised.
"""
from __future__ import annotations

import platform
import shutil
import socket
import sys

from app.core import runtime_paths as rp
from app.services import adb_client
from app.utils.adb_path import ADB, SCRCPY


def _c(id_, title, status, detail="", hint=""):
    return {"id": id_, "title": title, "status": status, "detail": detail, "hint": hint}


async def run_checks() -> list[dict]:
    out: list[dict] = []
    out.append(_c("os", "Sistem pengendalian", "INFO", f"{platform.platform()} · Python {sys.version.split()[0]}"
                  f"{' (frozen)' if rp.is_frozen() else ''}"))

    # data dir writable
    try:
        probe = rp.data_dir() / ".write_test"
        probe.write_text("x")
        probe.unlink()
        out.append(_c("data_dir", "Folder data pengguna", "PASS", str(rp.data_dir())))
    except OSError as exc:
        out.append(_c("data_dir", "Folder data pengguna", "FAIL", str(exc), "Semak kebenaran folder %APPDATA%\Mirrorhub."))

    free_gb = shutil.disk_usage(rp.data_dir()).free / 1024 ** 3
    out.append(_c("disk", "Ruang cakera", "PASS" if free_gb > 2 else "WARN" if free_gb > 0.5 else "FAIL",
                  f"{free_gb:.1f} GB bebas", "Kosongkan ruang untuk rakaman/muat naik." if free_gb <= 2 else ""))

    # adb
    if not ADB.exists():
        out.append(_c("adb", "ADB", "FAIL", f"Tiada di {ADB}", "Pasang semula Mirrorhub (adb.exe dibundel dalam pemasang)."))
    else:
        try:
            ver = await adb_client.adb_version()
            out.append(_c("adb", "ADB", "PASS", ver))
            await adb_client.start_server()
            devs = await adb_client.list_devices()
            usable = [d for d in devs if d.state == "device"]
            bad = [d for d in devs if d.state != "device"]
            out.append(_c("devices", "Peranti dikesan", "PASS" if usable else "WARN",
                          f"{len(usable)} sedia, {len(bad)} bermasalah",
                          "" if usable else "Sambung telefon (USB debugging ON) atau guna Pairing Center untuk WiFi."))
            for d in bad:
                out.append(_c(f"device:{d.serial}", f"Peranti {d.serial}", "WARN", d.state,
                              "Benarkan dialog 'Allow USB debugging' pada telefon." if d.state == "unauthorized"
                              else "Cabut/pasang semula kabel atau hidupkan semula Wireless Debugging."))
        except adb_client.AdbError as exc:
            out.append(_c("adb", "ADB", "FAIL", str(exc), "Tutup program lain yang menggunakan adb (Android Studio, Vysor) dan cuba lagi."))

    out.append(_c("scrcpy_server", "Pelayan skrin (scrcpy-server)", "PASS" if (ADB.parent / "scrcpy-server").exists() else "FAIL",
                  str(ADB.parent / "scrcpy-server"), "Fail ini wajib untuk strim embedded; pasang semula."))
    out.append(_c("scrcpy_exe", "scrcpy.exe (pilihan, tetingkap berasingan)", "PASS" if SCRCPY.exists() else "WARN", str(SCRCPY)))

    # port
    s = socket.socket()
    try:
        s.settimeout(0.3)
        busy = s.connect_ex(("127.0.0.1", 8000)) == 0
    finally:
        s.close()
    out.append(_c("port", "Port 8000 (localhost)", "INFO", "digunakan (mungkin oleh Mirrorhub ini)" if busy else "bebas"))

    try:
        import webview  # noqa: F401
        out.append(_c("webview", "Tetingkap desktop (pywebview)", "PASS"))
    except Exception as exc:
        out.append(_c("webview", "Tetingkap desktop (pywebview)", "WARN", str(exc), "Aplikasi boleh dibuka melalui pelayar pada http://127.0.0.1:8000."))
    return out


def summarize(checks: list[dict]) -> str:
    fails = sum(c["status"] == "FAIL" for c in checks)
    warns = sum(c["status"] == "WARN" for c in checks)
    return "FAIL" if fails else "WARN" if warns else "PASS"
