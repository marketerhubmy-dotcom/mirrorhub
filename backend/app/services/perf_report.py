"""
Diagnostic report builder (JSON / CSV / plain-text summary) with redaction.

Never included: environment variables, API keys, file contents, screen content, user names in paths,
phone serial numbers / full IP addresses (masked unless ``include_identifiers=True`` is explicitly requested).
"""
from __future__ import annotations

import csv
import io
import platform
import re
import sys
import time
from datetime import datetime, timezone

from app.services import perf_events
from app.version import VERSION

_IPV4 = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}\b")
_WIN_USER = re.compile(r"([A-Za-z]:\\Users\\)[^\\/\s\"']+", re.IGNORECASE)
_WIN_USER_SLASH = re.compile(r"([A-Za-z]:/Users/)[^\\/\s\"']+", re.IGNORECASE)
_SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|api[_-]?key\s*[=:]\s*\S+|password\s*[=:]\s*\S+|token\s*[=:]\s*\S+)", re.IGNORECASE)
_SERIAL = re.compile(r"\badb-([A-Za-z0-9]{4})[A-Za-z0-9]*-[A-Za-z0-9]+\._adb-tls-connect\._tcp\b")


def mask_serial(s: str | None) -> str | None:
    if not s:
        return s
    return s[:4] + "…" + s[-2:] if len(s) > 8 else "***"


def redact(text: str | None) -> str | None:
    """Mask IPs, secrets, Windows user names and mDNS serials inside free text."""
    if text is None:
        return None
    t = _SECRET.sub("[redacted]", str(text))
    t = _WIN_USER.sub(r"\1<user>", t)
    t = _WIN_USER_SLASH.sub(r"\1<user>", t)
    t = _SERIAL.sub(lambda m: f"adb-{m.group(1)}…", t)
    return _IPV4.sub(lambda m: f"{m.group(1)}.{m.group(2)}.x.x", t)


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds") if ts else None


def explain(row: dict) -> str:
    """One plain-language sentence for non-technical users (root-cause summary)."""
    h, name = row["health"], row["name"]
    if h == "authorization_required":
        return f"{name}: telefon belum memberi kebenaran. Buka kunci telefon dan tekan 'Allow' pada dialog USB/Wireless debugging."
    if h == "disconnected":
        return f"{name}: tidak disambungkan. Semak kabel, atau (WiFi) pastikan Wireless debugging hidup dan satu rangkaian dengan PC."
    if h == "reconnecting":
        return f"{name}: sedang menyambung semula; biasanya pulih sendiri dalam beberapa saat."
    if h == "degraded":
        r = row["health_reason"]
        if "reconnect" in r.lower():
            return f"{name}: sambungan berulang kali terputus. Cuba kabel/port USB lain, dekatkan telefon ke router, atau kurangkan bilangan strim."
        if "FPS rendah" in r:
            return f"{name}: strim perlahan semasa skrin bergerak. PC mungkin sibuk (lihat CPU) atau terlalu banyak strim; guna kualiti rendah dalam Sistem → Keutamaan."
        if "gagal" in r or "belum bermula" in r:
            return f"{name}: strim gagal bermula. Pastikan skrin telefon hidup dan tidak dilindungi, dan (Xiaomi) 'USB debugging (Security settings)' dihidupkan."
        return f"{name}: {r}"
    return f"{name}: berfungsi normal. {row['health_reason']}"


def build_report(collector, device_rows: list[dict], adb_info: dict, checks: list[dict] | None, *,
                 include_identifiers: bool = False, event_limit: int = 200) -> dict:
    ov = collector.overview(device_rows)

    def ident(v):
        return v if include_identifiers else redact(v) if isinstance(v, str) else v

    devices = []
    for r in device_rows:
        d = {k: r[k] for k in ("device_id", "name", "transport", "state", "online", "health", "health_reason", "fps", "fps_avg",
                               "resolution", "bitrate_kbps", "activity", "frames_sent", "frames_dropped_server", "client",
                               "startup_s", "reconnects", "reconnects_recent", "uptime_s", "battery",
                               "storage_free_mb", "storage_total_mb", "na")}
        d["last_error"] = ident(r["last_error"])
        d["streams"] = [{k: (ident(v) if k == "last_error" else v) for k, v in s.items() if k != "state_since"} for s in r["streams"]]
        d["summary"] = explain(r)
        devices.append(d)

    events = []
    for e in perf_events.recent(event_limit):
        events.append({"time": _iso(e["t"]), "kind": e["kind"], "level": e["level"],
                       "device_id": e["device_id"], "message": ident(e["message"])})

    th = ov["thresholds"]
    report = {
        "report": "mirrorhub-diagnostics",
        "generated_at": _iso(time.time()),
        "identifiers_included": include_identifiers,
        "app": {"version": VERSION, "python": sys.version.split()[0], "frozen": bool(getattr(sys, "frozen", False))},
        "system": {"os": platform.platform(), "cpu_count": ov["pc"]["cpu_count"], "ram_total_mb": ov["pc"]["ram_total_mb"]},
        "adb": {k: (ident(v) if isinstance(v, str) else v) for k, v in adb_info.items()},
        "overview": {k: ov[k] for k in ("devices", "devices_total", "active_streams", "pc", "process", "fps_avg", "ws", "reconnects", "health")},
        "thresholds": th,
        "alerts_active": ov["alerts"],
        "alerts_history": [{**a, "time": _iso(a["t"]), "message": ident(a["message"])} for a in list(collector.alert_history)[-50:]],
        "devices": devices,
        "events": events,
        "environment_checks": [{**c, "detail": ident(c.get("detail", ""))} for c in (checks or [])],
        "history_5m": collector.history("5m", 60),
        "summary": [d["summary"] for d in devices] or ["Tiada peranti didaftarkan."],
    }
    if not include_identifiers:
        for d in report["devices"]:
            d["device_id"] = d["device_id"][:8] + "…"
    return report


def to_text(report: dict) -> str:
    lines = [f"Mirrorhub diagnostic report — {report['generated_at']}",
             f"Versi {report['app']['version']} · {report['system']['os']}",
             f"Kesihatan sistem: {report['overview']['health']['status']} — {report['overview']['health']['reason']}", ""]
    pc, pr = report["overview"]["pc"], report["overview"]["process"]
    lines.append(f"PC: CPU {pc['cpu_pct']}% · RAM {pc['ram_pct']}% | Mirrorhub: CPU {pr['cpu_pct']}% · RSS {pr['rss_mb']} MB · threads {pr['threads']}")
    lines.append("")
    lines += [f"- {s}" for s in report["summary"]]
    if report["alerts_active"]:
        lines += ["", "Amaran aktif:"] + [f"- {a['title']}: {a['message']}" for a in report["alerts_active"]]
    lines += ["", "Peristiwa terkini:"] + [f"{e['time']} [{e['kind']}/{e['level']}] {e['message']}" for e in report["events"][-15:]]
    return "\n".join(lines)


def history_csv(rows: list[dict]) -> str:
    cols = ["t", "sys_cpu", "sys_ram_pct", "sys_ram_used_mb", "proc_cpu", "proc_rss_mb", "proc_threads", "proc_handles",
            "streams", "fps_avg", "reconnects", "ws", "devices_connected"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_utc"] + cols[1:])
    for r in rows:
        w.writerow([_iso(r["t"])] + [("" if r.get(c) is None else r.get(c)) for c in cols[1:]])
    return buf.getvalue()


def devices_csv(devices: list[dict]) -> str:
    cols = ["device_id", "name", "transport", "state", "health", "fps", "fps_avg", "resolution", "bitrate_kbps", "activity",
            "frames_sent", "frames_dropped_server", "startup_s", "reconnects", "uptime_s", "battery", "last_error"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for d in devices:
        w.writerow([("" if d.get(c) is None else d.get(c)) for c in cols])
    return buf.getvalue()


def events_csv(events: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time", "kind", "level", "device_id", "message"])
    for e in events:
        w.writerow([e["time"], e["kind"], e["level"], e["device_id"] or "", e["message"]])
    return buf.getvalue()
