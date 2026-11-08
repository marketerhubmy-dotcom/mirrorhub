"""
Mirrorhub Desktop entry point (also the PyInstaller entry via mirrorhub_app.py).

    MirrorHub.exe                 open the desktop window (starts the local backend)
    MirrorHub.exe --serve-only    backend only (no window); open http://127.0.0.1:<port> in a browser
    MirrorHub.exe --selftest      start backend, verify /health + UI + diagnostics, exit 0/1 (installer smoke test)
    MirrorHub.exe --diag          environment diagnostics (add --json)
    MirrorHub.exe --hwcheck ...   hardware validation (see app/tools/hwcheck.py)

Behaviour:
  * the API binds to 127.0.0.1 only;
  * if another Mirrorhub already answers on the port the window attaches to it (single backend);
  * if the port is taken by something else a free port is used;
  * if WebView2 / pywebview is unavailable the default browser is opened instead.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request

PREFERRED_PORT = 8000


def _ensure_std_streams() -> None:
    """Windowed builds start with sys.stdout/stderr = None; many libraries assume they exist."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def _probe(port: int, timeout: float = 1.0) -> str | None:
    """Return 'mirrorhub' if our /health answers, 'other' if the port is busy, None if free."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8", "replace"))
            if body.get("app") == "MirrorHub":
                return "mirrorhub"
    except Exception:
        pass
    s = socket.socket()
    try:
        s.settimeout(0.3)
        return "other" if s.connect_ex(("127.0.0.1", port)) == 0 else None
    finally:
        s.close()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Backend:
    def __init__(self, port: int):
        self.port = port
        self.server = None
        self.thread: threading.Thread | None = None
        self.error: BaseException | None = None

    def start(self) -> None:
        import uvicorn
        from app.main import app  # imported directly so PyInstaller bundles it

        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_config=None, access_log=False,
                                ws_per_message_deflate=False)  # H.264 is already compressed; deflate only burns CPU + ~110 KB per socket
        self.server = uvicorn.Server(config)

        def run() -> None:
            try:
                self.server.run()
            except BaseException as exc:  # surfaced by wait_ready
                self.error = exc
                logging.getLogger(__name__).exception("backend crashed")

        self.thread = threading.Thread(target=run, name="mirrorhub-backend", daemon=True)
        self.thread.start()

    def wait_ready(self, timeout: float = 40.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if self.error is not None or (self.thread and not self.thread.is_alive()):
                return False
            if _probe(self.port, 0.5) == "mirrorhub":
                return True
            time.sleep(0.25)
        return False

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=8)


def _acquire_backend(port: int | None) -> tuple[Backend | None, int]:
    """Attach to a running Mirrorhub or start one. Returns (backend_or_None, port)."""
    want = port or PREFERRED_PORT
    status = _probe(want)
    if status == "mirrorhub":
        return None, want
    if status == "other":
        want = _free_port()
    be = Backend(want)
    be.start()
    if not be.wait_ready():
        raise RuntimeError(f"Backend gagal bermula: {be.error or 'tamat masa'}")
    return be, want


def run_selftest(port: int | None) -> int:
    """Installer smoke test: no window, no phone needed."""
    checks: list[tuple[str, bool, str]] = []
    be = None
    try:
        be, p = _acquire_backend(port or _free_port())
        base = f"http://127.0.0.1:{p}"

        def get(path: str) -> tuple[int, bytes]:
            with urllib.request.urlopen(base + path, timeout=15) as r:
                return r.status, r.read()

        st, body = get("/health")
        checks.append(("health", st == 200 and b"MirrorHub" in body, body[:80].decode("utf-8", "replace")))
        st, body = get("/")
        checks.append(("frontend_index", st == 200 and b"<div id=\"root\">" in body, f"{len(body)} bytes"))
        st, body = get("/api/v1/system/about")
        checks.append(("about_api", st == 200 and b"version" in body, body[:60].decode("utf-8", "replace")))
        st, body = get("/api/v1/devices")
        checks.append(("devices_api", st == 200, f"{len(json.loads(body))} device row(s)"))
        st, body = get("/api/v1/system/diagnostics")
        diag = json.loads(body)
        by = {c["id"]: c for c in diag["checks"]}
        checks.append(("adb_present", by.get("adb", {}).get("status") == "PASS", by.get("adb", {}).get("detail", "")))
        checks.append(("scrcpy_server_present", by.get("scrcpy_server", {}).get("status") == "PASS", by.get("scrcpy_server", {}).get("detail", "")))
        checks.append(("data_dir_writable", by.get("data_dir", {}).get("status") == "PASS", by.get("data_dir", {}).get("detail", "")))
        # security: foreign Origin must be refused on a state-changing request
        req = urllib.request.Request(base + "/api/v1/pairing/refresh", method="POST", headers={"Origin": "http://evil.example"})
        try:
            urllib.request.urlopen(req, timeout=10)
            checks.append(("origin_guard", False, "evil origin was accepted"))
        except urllib.error.HTTPError as e:
            checks.append(("origin_guard", e.code == 403, f"HTTP {e.code}"))
    except Exception as exc:
        checks.append(("startup", False, str(exc)))
    finally:
        if be:
            be.stop()
    ok = all(c[1] for c in checks)
    for name, good, detail in checks:
        print(f"[{'PASS' if good else 'FAIL'}] {name}: {detail}")
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def open_window(url: str, backend: Backend | None) -> None:
    try:
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.create_window(title="MirrorHub", url=url, width=1360, height=860, min_size=(960, 620), text_select=True)
        webview.start(debug=False)
    except Exception as exc:  # no WebView2 / pythonnet problem: stay usable
        logging.getLogger(__name__).warning("desktop window unavailable (%s); opening browser", exc)
        import webbrowser
        webbrowser.open(url)
        if backend is not None:
            try:
                while backend.thread and backend.thread.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                pass


def main(argv: list[str] | None = None) -> int:
    _ensure_std_streams()
    ap = argparse.ArgumentParser(prog="MirrorHub", add_help=True)
    ap.add_argument("--serve-only", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--diag", action="store_true")
    ap.add_argument("--hwcheck", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--port", type=int)
    args, rest = ap.parse_known_args(argv)

    if args.diag:
        from app.tools import diag
        return diag.main(["--json"] if args.json else [])
    if args.hwcheck:
        from app.tools import hwcheck
        return hwcheck.main(rest)
    if args.selftest:
        return run_selftest(args.port)

    try:
        backend, port = _acquire_backend(args.port)
    except RuntimeError as exc:
        logging.getLogger(__name__).error("%s", exc)
        _fatal_message(str(exc))
        return 1

    url = f"http://127.0.0.1:{port}"
    try:
        if args.serve_only:
            while True:
                time.sleep(3600)
        open_window(url, backend)
    finally:
        if backend is not None:
            backend.stop()
    return 0


def _fatal_message(text: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, "MirrorHub", 0x10)
    except Exception:
        print(text, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
