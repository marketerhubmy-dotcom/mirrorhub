"""
Performance collector for the Performance dashboard (V1.1).

Design rules
* Everything shown is measured.  When a value cannot be measured the field is ``None`` and the API adds a
  human reason in ``na`` – the UI shows ``N/A`` + reason, never a made-up number.
* Bounded memory: 1 h of 2 s samples (ring buffer) + 24 h of 30 s aggregates + capped event/alert logs.
* Cheap when idle: one 2 s tick that reads in-memory counters and two ctypes calls; no subprocesses, no DB
  access except an optional 10 s device count.
* "Idle" is not "broken": a static phone screen makes scrcpy send (almost) no frames.  Activity is judged
  from byte rate; FPS thresholds only apply to *active* streams.  Stalled = transport/device problem, not low FPS.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.services import perf_events
from app.services.metrics import process_metrics
from app.services.sysmetrics import ProcessCpu, SystemMonitor

logger = logging.getLogger("mirrorhub.perf")

SAMPLE_INTERVAL_S = 2.0
FINE_MAX = 1800          # 1 h @ 2 s
COARSE_BUCKET_S = 30.0
COARSE_MAX = 2880        # 24 h @ 30 s
IDLE_BYTES_PER_S = 15360  # recent (~6 s) byte rate below this = "idle" (static screen / clock tick), not "slow"
WARMUP_S = 10.0           # the first seconds after the first frame carry the initial keyframe burst; never judged
RANGES = {"5m": 300, "15m": 900, "1h": 3600}

# ── thresholds (persisted through preferences; documented in docs/PERFORMANCE_DASHBOARD.md) ──
THRESHOLD_DEFAULTS: dict[str, Any] = {
    "perf_ram_high_pct": 90,
    "perf_cpu_high_pct": 90,
    "perf_cpu_sustain_s": 30,
    "perf_fps_low": 5,
    "perf_reconnect_loop_count": 5,      # reconnects within perf_reconnect_window_s
    "perf_reconnect_window_s": 120,
    "perf_startup_slow_s": 10,
    "perf_max_streams": 8,
    "perf_rss_growth_mb": 150,
    "perf_alerts_enabled": True,
    "perf_alert_cooldown_s": 300,
}


# ── websocket gauge ───────────────────────────────────────────────────────────

_ws_counts: dict[str, int] = {}


@contextlib.contextmanager
def track_ws(kind: str):
    """Count open websockets by kind (video/control/devices). Always balanced, even on errors."""
    _ws_counts[kind] = _ws_counts.get(kind, 0) + 1
    try:
        yield
    finally:
        _ws_counts[kind] = max(0, _ws_counts.get(kind, 1) - 1)


def ws_snapshot() -> dict[str, int]:
    return dict(_ws_counts)


# ── alert state machine ───────────────────────────────────────────────────────

@dataclass
class AlertState:
    key: str
    scope: str                 # "system" or a device_id
    title: str
    severity: str = "warning"
    active: bool = False
    since: float = 0.0
    last_value: Any = None
    message: str = ""
    last_notified: float = float("-inf")      # first trigger always notifies
    cleared_at: float = 0.0
    _trig: int = 0
    _clear: int = 0

    def public(self) -> dict:
        return {"key": self.key, "scope": self.scope, "title": self.title, "severity": self.severity,
                "active": self.active, "since": self.since, "value": self.last_value, "message": self.message}


def hysteresis(state: AlertState, *, trigger: bool, clear: bool, need_trigger: int, need_clear: int,
               now: float, cooldown: float, value: Any, message: str, notify: Callable[[AlertState, str], None]) -> None:
    """
    Trigger after `need_trigger` consecutive ticks where `trigger` holds; clear after `need_clear` consecutive
    ticks where `clear` holds (a band between the two keeps the state).  A re-trigger within `cooldown` seconds of
    the last notification stays active but silent, so flapping conditions do not spam the user.
    """
    state.last_value = value
    if not state.active:
        state._trig = state._trig + 1 if trigger else 0
        if state._trig >= need_trigger:
            state.active, state.since, state.message, state._trig, state._clear = True, now, message, 0, 0
            if now - state.last_notified >= cooldown:
                state.last_notified = now
                notify(state, "triggered")
    else:
        state.message = message if trigger else state.message
        state._clear = state._clear + 1 if clear else 0
        if state._clear >= need_clear:
            state.active, state.cleared_at, state._clear, state._trig = False, now, 0, 0
            notify(state, "cleared")


# ── helpers ───────────────────────────────────────────────────────────────────

def _mean(vals: list[float | None]) -> float | None:
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 2) if v else None


def downsample(samples: list[dict], max_points: int = 240) -> list[dict]:
    """Bucket-average numeric fields so charts stay light; None-aware, keeps first timestamp of each bucket."""
    n = len(samples)
    if n <= max_points:
        return samples
    size = -(-n // max_points)
    out = []
    for i in range(0, n, size):
        chunk = samples[i:i + size]
        row: dict[str, Any] = {"t": chunk[0]["t"]}
        for k in chunk[0]:
            if k == "t":
                continue
            vals = [c.get(k) for c in chunk]
            if k in ("reconnects",):                      # counts add up inside a bucket
                row[k] = sum(v for v in vals if v) or 0
            else:
                row[k] = _mean(vals) if all(isinstance(v, (int, float)) or v is None for v in vals) else vals[-1]
        out.append(row)
    return out


def classify_health(*, device_state: str, online: bool, stream: dict | None, now: float, th: dict,
                    recent_reconnects: int) -> tuple[str, str]:
    """
    Returns (health, reason).  health ∈ healthy | degraded | reconnecting | disconnected | authorization_required.
    See docs/PERFORMANCE_DASHBOARD.md for the interpretation table.
    """
    if device_state == "unauthorized":
        return "authorization_required", "Telefon belum membenarkan PC ini (Allow USB/Wireless debugging)."
    if device_state == "reconnecting":
        return "reconnecting", "Menyambung semula peranti."
    if not online:
        return "disconnected", "Peranti tidak disambungkan."
    if stream is None:
        return "healthy", "Peranti online; tiada strim dibuka."
    st = stream["state"]
    if st in ("starting", "reconnecting"):
        waited = now - stream["state_since"]
        if st == "reconnecting":
            return "reconnecting", "Strim menyambung semula" + (f" (sudah {int(waited)} s)." if waited > 5 else ".")
        if waited > 30:
            return "degraded", f"Strim belum bermula selepas {int(waited)} s."
        return "healthy", "Strim sedang dimulakan."
    if st == "failed":
        return "degraded", "Strim gagal: " + (stream.get("last_error") or "sebab tidak diketahui")[:120]
    if st == "stopped" or st == "idle":
        return "healthy", "Strim dihentikan (tiada penonton)."
    # streaming
    if recent_reconnects >= th["perf_reconnect_loop_count"]:
        return "degraded", f"{recent_reconnects} sambungan semula dalam {th['perf_reconnect_window_s']} s (gelung reconnect)."
    # judged on the last ~6 s and only after sustained activity: a brief notification blip is not a slow stream
    if (stream["activity"] == "active" and stream.get("active_streak", 0) >= 3 and stream.get("fps_recent") is not None
            and stream["fps_recent"] < th["perf_fps_low"]):
        return "degraded", f"FPS rendah ({stream['fps_recent']}) semasa skrin aktif."
    if stream["startup_s"] is not None and stream["startup_s"] > th["perf_startup_slow_s"]:
        return "degraded", f"Strim lambat bermula ({stream['startup_s']} s)."
    if stream["activity"] == "idle":
        return "healthy", "Strim hidup; skrin statik (tiada bingkai baharu adalah normal)."
    return "healthy", "Strim lancar."


# ── collector ─────────────────────────────────────────────────────────────────

class PerfCollector:
    def __init__(
        self,
        *,
        sessions: Callable[[], list],
        monitor_snapshot: Callable[[], dict],
        device_source: Callable[[], Awaitable[list[dict]]] | None = None,
        thresholds: Callable[[], dict] | None = None,
        interval: float = SAMPLE_INTERVAL_S,
        clock: Callable[[], float] = time.time,
        sysmon: SystemMonitor | None = None,
    ):
        self._sessions = sessions
        self._monitor = monitor_snapshot
        self._device_source = device_source
        self._rows: list[dict] = []
        self._rows_at = 0.0
        self._thresholds = thresholds or (lambda: dict(THRESHOLD_DEFAULTS))
        self.interval = interval
        self._clock = clock
        self._sys = sysmon or SystemMonitor()
        self._pcpu = ProcessCpu()
        self.fine: deque[dict] = deque(maxlen=FINE_MAX)
        self.coarse: deque[dict] = deque(maxlen=COARSE_MAX)
        self._bucket: list[dict] = []
        self._bucket_start = 0.0
        self.started_at = clock()
        self._task: asyncio.Task | None = None
        self._prev_counters: dict[tuple[str, str], tuple[float, int, int, int]] = {}   # key -> (t, frames, bytes, reconnects)
        self._rates: dict[tuple[str, str], dict] = {}
        self._fps_hist: dict[tuple[str, str], deque] = {}
        self._streak: dict[tuple[str, str], int] = {}            # consecutive ticks of real activity
        self._bytes_hist: dict[tuple[str, str], deque] = {}      # last 3 per-interval byte rates (~6 s)
        self._state_since: dict[tuple[str, str], tuple[str, float]] = {}
        self._reconnect_ts: dict[str, deque] = {}        # device_id -> timestamps of reconnects
        self._reconnect_total = 0
        self._dev_reconnects: dict[str, int] = {}          # cumulative per device (survives session replacement)
        self._last_reconnect_seen: dict[tuple[str, str], int] = {}
        self.client_stats: dict[str, dict] = {}
        self.alerts: dict[tuple[str, str], AlertState] = {}
        self.alert_history: deque[dict] = deque(maxlen=200)
        self._db_counts = {"registered": 0, "online": 0}
        self._db_counts_at = 0.0
        self._cpu_high_ticks = 0
        self.last_sample: dict | None = None
        self._ticks = 0
        self._pc_static: dict = {"ram_total_mb": None, "cpu_count": os.cpu_count()}

    # ── lifecycle ──
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="perf-collector")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("perf tick failed")
            await asyncio.sleep(self.interval)

    # ── device registry cache (keeps dashboard polling off the database) ──
    DEVICE_CACHE_S = 5.0

    async def refresh_devices(self, now: float | None = None, force: bool = False) -> list[dict]:
        now = self._clock() if now is None else now
        if self._device_source and (force or now - self._rows_at >= self.DEVICE_CACHE_S):
            try:
                self._rows = await self._device_source()
                self._rows_at = now
                self._db_counts = {"registered": len(self._rows), "online": sum(1 for r in self._rows if r["is_online"])}
            except Exception:
                logger.debug("device source failed", exc_info=True)
        return self._rows

    def invalidate_devices(self, *_a) -> None:
        """A lifecycle event happened: the next read refreshes the registry rows."""
        self._rows_at = 0.0

    # ── sampling ──
    async def tick(self) -> dict:
        now = self._clock()
        self._ticks += 1
        await self.refresh_devices(now)

        sysm = self._sys.sample()
        self._pc_static = {"ram_total_mb": sysm.ram_total_mb, "cpu_count": sysm.cpu_count}
        proc = process_metrics()
        proc_cpu = self._pcpu.sample()
        snap = self._monitor() or {}
        adb_devs = snap.get("devices", [])
        connected = sum(1 for d in adb_devs if d.get("state") == "device")
        unauth = sum(1 for d in adb_devs if d.get("state") == "unauthorized")
        registered = self._db_counts.get("registered", 0)
        disconnected = max(0, registered - connected - unauth) if registered else 0

        sess_list = list(self._sessions())
        now_mono = time.monotonic()
        fps_vals: list[float] = []
        active = 0
        reconnect_delta = 0
        for s in sess_list:
            key = (s.device_id, s.profile)
            frames, nbytes = s.hub.frames, s.hub.bytes
            prev = self._prev_counters.get(key)
            fps = brate = None
            if prev and now > prev[0]:
                dt = now - prev[0]
                fps = round(max(0, frames - prev[1]) / dt, 2)
                brate = max(0, nbytes - prev[2]) / dt
            self._prev_counters[key] = (now, frames, nbytes, s.reconnects)
            seen = self._last_reconnect_seen.get(key, 0)
            if s.reconnects > seen:
                n = s.reconnects - seen
                reconnect_delta += n
                self._reconnect_total += n
                self._dev_reconnects[s.device_id] = self._dev_reconnects.get(s.device_id, 0) + n
                q = self._reconnect_ts.setdefault(s.device_id, deque(maxlen=200))
                q.extend([now] * n)
            self._last_reconnect_seen[key] = s.reconnects
            prev_state = self._state_since.get(key)
            if not prev_state or prev_state[0] != s.state:
                self._state_since[key] = (s.state, now)
            if fps is not None:
                h = self._fps_hist.setdefault(key, deque(maxlen=15))     # rolling ~30 s
                h.append((fps, brate or 0.0))
                bh = self._bytes_hist.setdefault(key, deque(maxlen=3))
                bh.append(brate or 0.0)
                self._rates[key] = {"fps": fps, "bitrate_kbps": round((brate or 0) * 8 / 1000, 1),
                                    "fps_avg": round(statistics.fmean(x[0] for x in h), 2),
                                    "bytes_per_s": statistics.fmean(x[1] for x in h),
                                    "recent_bytes_per_s": statistics.fmean(bh),
                                    "fps_recent": round(statistics.fmean(x[0] for x in list(h)[-3:]), 2)}
                self._streak[key] = self._streak.get(key, 0) + 1 if statistics.fmean(bh) >= IDLE_BYTES_PER_S else 0
            if s.state == "streaming":
                active += 1
                if self._activity(s, now_mono) == "active":
                    fps_vals.append(self._rates[key]["fps_avg"])
        # forget counters of sessions that no longer exist
        live = {(s.device_id, s.profile) for s in sess_list}
        for d in (self._prev_counters, self._rates, self._fps_hist, self._bytes_hist, self._streak, self._state_since, self._last_reconnect_seen):
            for k in [k for k in d if k not in live]:
                d.pop(k, None)

        ws = ws_snapshot()
        sample = {
            "t": round(now, 2),
            "sys_cpu": sysm.cpu_pct, "sys_ram_pct": sysm.ram_pct, "sys_ram_used_mb": sysm.ram_used_mb,
            "proc_cpu": proc_cpu, "proc_rss_mb": proc.get("rss_mb"), "proc_threads": proc.get("threads"),
            "proc_handles": proc.get("handles"),
            "streams": active, "fps_avg": _mean(fps_vals), "reconnects": reconnect_delta,
            "ws": sum(ws.values()), "devices_connected": connected,
        }
        self.fine.append(sample)
        self.last_sample = sample
        self._coarse_add(sample)
        self._evaluate_alerts(now, sample, sysm, sess_list)
        return sample

    def _coarse_add(self, s: dict) -> None:
        if not self._bucket:
            self._bucket_start = s["t"]
        self._bucket.append(s)
        if s["t"] - self._bucket_start >= COARSE_BUCKET_S:
            agg = downsample(self._bucket, 1)[0] if len(self._bucket) > 1 else dict(self._bucket[0])
            agg["reconnects"] = sum(b["reconnects"] for b in self._bucket)
            self.coarse.append(agg)
            self._bucket = []

    # ── history ──
    def history(self, rng: str = "5m", max_points: int = 240) -> list[dict]:
        if rng in RANGES:
            cutoff = self._clock() - RANGES[rng]
            rows = [s for s in self.fine if s["t"] >= cutoff]
            if rng == "1h" and len(self.fine) < FINE_MAX and not rows:
                rows = list(self.fine)
        else:  # "session": coarse history + the recent fine tail
            last_c = self.coarse[-1]["t"] if self.coarse else 0
            rows = list(self.coarse) + [s for s in self.fine if s["t"] > last_c + COARSE_BUCKET_S]
        return downsample(rows, max_points)

    # ── alerts ──
    def thresholds(self) -> dict:
        th = dict(THRESHOLD_DEFAULTS)
        th.update(self._thresholds() or {})
        return th

    def _notify(self, st: AlertState, what: str) -> None:
        level = "warn" if what == "triggered" else "info"
        msg = f"{st.title}: {st.message}" if what == "triggered" else f"{st.title}: pulih"
        rec = {"t": self._clock(), "key": st.key, "scope": st.scope, "event": what, "severity": st.severity, "message": msg}
        self.alert_history.append(rec)
        if self.thresholds().get("perf_alerts_enabled", True) or what == "cleared":
            perf_events.emit("alert", msg, device_id=None if st.scope == "system" else st.scope, level=level,
                             alert=st.key, event=what, severity=st.severity)

    def _state(self, key: str, scope: str, title: str, severity: str = "warning") -> AlertState:
        k = (key, scope)
        if k not in self.alerts:
            self.alerts[k] = AlertState(key=key, scope=scope, title=title, severity=severity)
        return self.alerts[k]

    def _evaluate_alerts(self, now: float, sample: dict, sysm, sessions: list) -> None:
        th = self.thresholds()
        cd = float(th["perf_alert_cooldown_s"])
        tick_s = max(self.interval, 0.001)
        sustain = max(1, int(th["perf_cpu_sustain_s"] / tick_s))

        def run(st, trig, clr, need_t, need_c, val, msg):
            hysteresis(st, trigger=trig, clear=clr, need_trigger=need_t, need_clear=need_c, now=now, cooldown=cd,
                       value=val, message=msg, notify=self._notify)

        ram = sample["sys_ram_pct"]
        if ram is not None:
            hi = float(th["perf_ram_high_pct"])
            run(self._state("ram_high", "system", "RAM PC tinggi"), ram >= hi, ram < hi - 5, 3, 5, ram,
                f"RAM digunakan {ram:.0f}% (ambang {hi:.0f}%).")
        cpu = sample["sys_cpu"]
        if cpu is not None:
            hi = float(th["perf_cpu_high_pct"])
            run(self._state("cpu_high", "system", "CPU PC tinggi berterusan"), cpu >= hi, cpu < hi - 15, sustain, 5, cpu,
                f"CPU {cpu:.0f}% selama ≥ {int(th['perf_cpu_sustain_s'])} s.")
        n = sample["streams"]
        mx = int(th["perf_max_streams"])
        run(self._state("too_many_streams", "system", "Terlalu banyak strim aktif"), n > mx, n <= mx, 2, 3, n,
            f"{n} strim aktif (had disyorkan {mx}). Guna profil rendah atau jeda tile.")
        # process memory growth over ~10 min
        rss = sample["proc_rss_mb"]
        if rss is not None and len(self.fine) >= int(300 / tick_s):
            window = [s["proc_rss_mb"] for s in list(self.fine)[-int(600 / tick_s):] if s["proc_rss_mb"] is not None]
            growth = rss - min(window) if window else 0
            lim = float(th["perf_rss_growth_mb"])
            run(self._state("memory_growth", "system", "Memori proses Mirrorhub meningkat"), growth >= lim and rss >= window[0],
                growth < lim * 0.6, 3, 10, round(growth, 1), f"RSS naik {growth:.0f} MB dalam ≤ 10 min (ambang {lim:.0f} MB).")
        # per device
        win = float(th["perf_reconnect_window_s"])
        for s in sessions:
            q = self._reconnect_ts.get(s.device_id)
            recent = sum(1 for ts in q if now - ts <= win) if q else 0
            lim = int(th["perf_reconnect_loop_count"])
            run(self._state("reconnect_loop", s.device_id, "Gelung reconnect", "critical"), recent >= lim, recent == 0, 1, 2,
                recent, f"{recent} sambungan semula dalam {int(win)} s.")
            since = self._state_since.get((s.device_id, s.profile), (s.state, now))[1]
            stalled = (s.state == "failed") or (s.state == "reconnecting" and now - since > 60) or (s.state == "starting" and now - since > 45)
            run(self._state("stream_stalled", s.device_id, "Strim tersangkut", "critical"), stalled, not stalled, 1, 2,
                s.state, f"Strim {s.profile} dalam keadaan '{s.state}' lebih lama daripada biasa.")

    def active_alerts(self) -> list[dict]:
        return [a.public() for a in self.alerts.values() if a.active]

    # ── client-side decoder stats (reported by the Device Wall tile) ──
    def report_client(self, device_id: str, profile: str, *, received: int, decoded: int, dropped: int,
                      fps: float | None, width: int | None, height: int | None) -> None:
        if len(self.client_stats) > 256 and device_id not in self.client_stats:
            return                                   # bounded: ignore unknown ids beyond a sane count
        self.client_stats[device_id] = {"t": self._clock(), "profile": profile, "received": int(received), "decoded": int(decoded),
                                        "dropped": int(dropped), "fps": fps, "width": width, "height": height}

    # ── per-device table / overview ──
    def _activity(self, s, now_mono: float) -> str:
        """active | idle | warmup | unknown | none — judged on the last ~6 s of traffic, never on the stream start burst."""
        if s.state != "streaming":
            return "none"
        key = (s.device_id, s.profile)
        r = self._rates.get(key)
        if r is None:
            return "unknown"
        if s.hub.first_frame_at and now_mono - s.hub.first_frame_at < WARMUP_S:
            return "warmup"
        return "active" if r["recent_bytes_per_s"] >= IDLE_BYTES_PER_S else "idle"

    def stream_view(self, s) -> dict:
        key = (s.device_id, s.profile)
        r = self._rates.get(key)
        now = self._clock()
        activity = self._activity(s, time.monotonic())
        return {
            "profile": s.profile, "state": s.state, "state_since": self._state_since.get(key, (s.state, now))[1],
            "viewers": len(s.hub.viewers), "frames": s.hub.frames, "bytes": s.hub.bytes, "dropped_server": s.hub.dropped,
            "fps": r["fps"] if r else None, "fps_avg": r["fps_avg"] if r else None,
            "fps_recent": r["fps_recent"] if r else None, "active_streak": self._streak.get(key, 0),
            "bitrate_kbps": r["bitrate_kbps"] if r else None,
            "width": s.hub.width or None, "height": s.hub.height or None,
            "startup_s": s.startup_seconds(), "reconnects": s.reconnects,
            "last_error": s.last_error_msg or None, "last_error_at": s.last_error_wall or None,
            "uptime_s": round(time.monotonic() - s.started_at, 1) if s.started_at and s.state == "streaming" else None,
            "activity": activity,
        }

    def device_rows(self, devices: list[dict]) -> list[dict]:
        """devices: registry rows (dict) supplied by the API layer."""
        now = self._clock()
        th = self.thresholds()
        by_dev: dict[str, list] = {}
        for s in self._sessions():
            by_dev.setdefault(s.device_id, []).append(s)
        out = []
        for d in devices:
            sess = by_dev.get(d["device_id"], [])
            views = sorted((self.stream_view(s) for s in sess), key=lambda v: (-v["viewers"], -(v["width"] or 0)))
            primary = views[0] if views else None
            q = self._reconnect_ts.get(d["device_id"])
            recent = sum(1 for ts in q if now - ts <= th["perf_reconnect_window_s"]) if q else 0
            health, reason = classify_health(device_state=d["state"], online=d["is_online"], stream=primary, now=now, th=th,
                                             recent_reconnects=recent)
            cs = self.client_stats.get(d["device_id"])
            client = None
            if cs and now - cs["t"] <= 20:
                client = {k: cs[k] for k in ("profile", "received", "decoded", "dropped", "fps")} | {"age_s": round(now - cs["t"], 1)}
            na: dict[str, str] = {}
            if primary is None:
                for f in ("fps", "bitrate_kbps", "resolution", "startup_s", "uptime_s"):
                    na[f] = "Tiada strim aktif untuk peranti ini."
            else:
                if primary["fps"] is None:
                    na["fps"] = "Belum ada sampel (strim baru dibuka)."
                if primary["width"] is None:
                    na["resolution"] = "Belum menerima keyframe."
                if primary["startup_s"] is None:
                    na["startup_s"] = "Belum ada bingkai pertama."
                if primary["uptime_s"] is None:
                    na["uptime_s"] = "Strim belum berjalan."
            if client is None:
                na["client"] = "Tiada tile Device Wall terbuka melaporkan statistik penyahkod."
            if not d.get("storage_total_mb"):
                na["storage"] = "Tidak dibaca daripada peranti."
            out.append({
                "device_id": d["device_id"], "name": d["name"], "transport": d["transport"] or None, "state": d["state"],
                "online": d["is_online"], "health": health, "health_reason": reason,
                "fps": primary["fps"] if primary else None, "fps_avg": primary["fps_avg"] if primary else None,
                "resolution": f"{primary['width']}x{primary['height']}" if primary and primary["width"] else None,
                "bitrate_kbps": primary["bitrate_kbps"] if primary else None,
                "activity": primary["activity"] if primary else "none",
                "frames_sent": sum(v["frames"] for v in views), "frames_dropped_server": sum(v["dropped_server"] for v in views),
                "client": client,
                "startup_s": primary["startup_s"] if primary else None,
                "reconnects": self._dev_reconnects.get(d["device_id"], 0), "reconnects_recent": recent,
                "last_error": next((v["last_error"] for v in views if v["last_error"]), None) or (d.get("last_error") or None),
                "uptime_s": primary["uptime_s"] if primary else None,
                "battery": d.get("battery") if d["is_online"] else None,
                "storage_free_mb": d.get("storage_free_mb") or None, "storage_total_mb": d.get("storage_total_mb") or None,
                "streams": views, "na": na,
            })
        return out

    def overview(self, device_rows: list[dict]) -> dict:
        s = self.last_sample or {}
        th = self.thresholds()
        counts = {"connected": 0, "unauthorized": 0, "disconnected": 0, "reconnecting": 0}
        for r in device_rows:
            if r["health"] == "authorization_required":
                counts["unauthorized"] += 1
            elif r["health"] == "reconnecting":
                counts["reconnecting"] += 1
            elif r["online"]:
                counts["connected"] += 1
            else:
                counts["disconnected"] += 1
        now = self._clock()
        rc = {"5m": 0, "15m": 0, "1h": 0}
        for dq in self._reconnect_ts.values():
            for ts in dq:
                for k, secs in RANGES.items():
                    if now - ts <= secs:
                        rc[k] += 1
        worst = "healthy"
        order = {"healthy": 0, "degraded": 1, "reconnecting": 2, "authorization_required": 2, "disconnected": 1}
        for r in device_rows:
            if r["online"] or r["health"] in ("authorization_required", "reconnecting"):
                if order.get(r["health"], 0) > order.get(worst, 0):
                    worst = r["health"]
        crit = [a for a in self.active_alerts() if a["severity"] == "critical"]
        system_health = "degraded" if (self.active_alerts() or worst != "healthy") else "healthy"
        reason = "; ".join(a["title"] for a in self.active_alerts()[:3]) or (
            f"{sum(1 for r in device_rows if r['health'] == 'degraded')} peranti bermasalah" if worst != "healthy" else "Semua normal.")
        return {
            "generated_at": now, "collector_uptime_s": round(now - self.started_at),
            "devices": counts, "devices_total": len(device_rows),
            "active_streams": s.get("streams", 0),
            "pc": {"cpu_pct": s.get("sys_cpu"), "ram_pct": s.get("sys_ram_pct"), "ram_used_mb": s.get("sys_ram_used_mb"),
                   "ram_total_mb": self._pc_static["ram_total_mb"], "cpu_count": self._pc_static["cpu_count"]},
            "process": {"cpu_pct": s.get("proc_cpu"), "rss_mb": s.get("proc_rss_mb"), "threads": s.get("proc_threads"),
                        "handles": s.get("proc_handles"),
                        "note": "Proses backend Mirrorhub (termasuk tetingkap pywebview). Proses WebView2 dan adb dikira berasingan oleh Windows."},
            "fps_avg": s.get("fps_avg"),
            "fps_note": None if s.get("fps_avg") is not None else "N/A: tiada strim aktif atau semua strim idle (skrin statik).",
            "ws": ws_snapshot(), "ws_total": s.get("ws", 0),
            "reconnects": rc,
            "health": {"status": system_health, "reason": reason, "critical_alerts": len(crit)},
            "alerts": self.active_alerts(),
            "thresholds": th,
            "samples": {"fine": len(self.fine), "coarse": len(self.coarse), "events": len(perf_events.recent(1000))},
        }



# module singleton (wired in app.main lifespan)
_collector: PerfCollector | None = None


def get_collector() -> PerfCollector:
    global _collector
    if _collector is None:
        from app.devices.lifecycle import get_monitor
        from app.services import preferences
        from app.services.scrcpy_stream import stream_manager

        def th() -> dict:
            p = preferences.load()
            return {k: p[k] for k in THRESHOLD_DEFAULTS if k in p}

        async def device_source() -> list[dict]:
            from app.devices import registry
            from app.models.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                rows = await registry.get_all_devices(db)
            out = []
            for d in rows:
                state = d.state if d.state and d.state != "absent" else ("online" if d.is_online else "offline")
                out.append({"device_id": d.device_id, "name": d.device_name, "transport": d.transport or ("wifi" if d.wifi else "usb"),
                            "state": state, "is_online": bool(d.is_online), "battery": d.battery,
                            "storage_free_mb": d.storage_free_mb, "storage_total_mb": d.storage_total_mb, "last_error": d.last_error})
            return out

        _collector = PerfCollector(sessions=stream_manager.sessions, monitor_snapshot=lambda: get_monitor().snapshot(),
                                   device_source=device_source, thresholds=th)
        perf_events.subscribe(lambda ev: _collector.invalidate_devices() if ev["kind"] in ("device", "adb") else None)
    return _collector
