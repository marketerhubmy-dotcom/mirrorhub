"""Performance collector, health classification, alert hysteresis, SPS parser, event log, report redaction."""
import asyncio
import types

import pytest

from app.services import perf, perf_events, perf_report
from app.services import scrcpy_stream as ss
from app.services.sysmetrics import ProcessCpu, SystemMonitor


@pytest.fixture(autouse=True)
def clean_events():
    perf_events.reset()
    perf._ws_counts.clear()
    yield
    perf_events.reset()


# ── system metrics ────────────────────────────────────────────────────────────

class FakeSys(SystemMonitor):
    def __init__(self, times, mem=(4000.0, 16000.0)):
        super().__init__()
        self.available = True
        self._seq = list(times)
        self._mem = mem

    def _times(self):
        return self._seq.pop(0) if self._seq else None

    def _memory(self):
        return self._mem


def test_cpu_percent_from_deltas_and_ram():
    m = FakeSys([(0, 0, 0), (50, 100, 0)])          # idle 50 of 100 busy-total -> 50 %
    first = m.sample()
    assert first.cpu_pct is None                     # needs two samples: N/A, not 0
    s = m.sample()
    assert s.cpu_pct == 50.0 and s.ram_pct == 25.0 and s.ram_total_mb == 16000.0


def test_unavailable_platform_returns_none_not_zero():
    m = SystemMonitor()
    m.available = False
    s = m.sample()
    assert (s.cpu_pct, s.ram_pct, s.ram_used_mb) == (None, None, None)


def test_system_errors_degrade_to_none():
    class Boom(FakeSys):
        def _memory(self):
            raise OSError("x")
    s = Boom([(0, 0, 0)]).sample()
    assert s.ram_pct is None


def test_process_cpu_is_bounded():
    p = ProcessCpu()
    x = sum(i * i for i in range(200000))
    assert 0.0 <= p.sample() <= 100.0 and x


# ── event log ─────────────────────────────────────────────────────────────────

def test_event_log_is_bounded_and_filterable():
    for i in range(perf_events.MAX_EVENTS + 250):
        perf_events.emit("stream", f"e{i}", device_id="a" if i % 2 else "b")
    ev = perf_events.recent(5000)
    assert len(ev) == perf_events.MAX_EVENTS
    assert all(e["device_id"] == "a" for e in perf_events.recent(50, device_id="a"))
    assert perf_events.recent(1)[0]["message"].startswith("e")
    assert perf_events.emit("weird-kind", "x")["kind"] == "system"


def test_broken_listener_never_breaks_emit():
    def bad(_):
        raise RuntimeError("boom")
    perf_events.subscribe(bad)
    try:
        assert perf_events.emit("system", "ok")["message"] == "ok"
    finally:
        perf_events.unsubscribe(bad)


# ── SPS parser (round-trip with a bit writer) ─────────────────────────────────

class BW:
    def __init__(self):
        self.bits = []

    def u(self, n, v):
        self.bits += [(v >> (n - 1 - i)) & 1 for i in range(n)]

    def ue(self, v):
        v += 1
        n = v.bit_length()
        self.u(n - 1, 0)
        self.u(n, v)

    def bytes(self):
        b = self.bits + [1]
        while len(b) % 8:
            b.append(0)
        return bytes(int("".join(map(str, b[i:i + 8])), 2) for i in range(0, len(b), 8))


def make_sps(w, h, profile=66, crop_right_px=0, crop_bottom_px=0):
    mbs_w, mbs_h = -(-w // 16), -(-h // 16)
    bw = BW()
    bw.u(8, profile); bw.u(8, 0); bw.u(8, 31)
    bw.ue(0)
    if profile == 100:
        bw.ue(1); bw.ue(0); bw.ue(0); bw.u(1, 0); bw.u(1, 0)
    bw.ue(0); bw.ue(0); bw.ue(0)                      # log2_max_frame_num, poc type 0, log2_max_poc
    bw.ue(1); bw.u(1, 0)
    bw.ue(mbs_w - 1); bw.ue(mbs_h - 1)
    bw.u(1, 1); bw.u(1, 1)                            # frame_mbs_only, direct_8x8
    if crop_right_px or crop_bottom_px:
        bw.u(1, 1); bw.ue(0); bw.ue(crop_right_px // 2); bw.ue(0); bw.ue(crop_bottom_px // 2)
    else:
        bw.u(1, 0)
    bw.u(1, 0)                                        # vui
    return b"\x00\x00\x00\x01\x67" + bw.bytes()


@pytest.mark.parametrize("w,h,profile,cr,cb", [
    (432, 960, 66, 0, 0), (540, 1200, 100, 4, 0), (1080, 2400, 66, 8, 0), (1080, 1920, 100, 8, 0), (720, 1280, 66, 0, 0),
])
def test_sps_size_roundtrip(w, h, profile, cr, cb):
    sps = make_sps(w, h, profile, cr, cb)
    assert ss.parse_sps_size(sps) == (w, h)


def test_sps_garbage_returns_none():
    assert ss.parse_sps_size(b"\x00\x00\x00\x01\x67\xff") is None
    assert ss.parse_sps_size(b"") is None


def test_hub_records_resolution_frames_and_drops():
    hub = ss.StreamHub(viewer_queue=1)
    sps = make_sps(432, 960)
    pps = b"\x00\x00\x00\x01\x68\xce\x3c\x80"
    idr = b"\x00\x00\x00\x01\x65" + bytes(50)
    v = hub.subscribe()
    hub.push(sps + pps + idr)
    assert (hub.width, hub.height) == (432, 960) and hub.frames == 1 and hub.first_frame_at > 0
    for _ in range(5):                                # viewer queue (1 + GOP) overflows -> backpressure counted
        hub.push(b"\x00\x00\x00\x01\x41" + bytes(20))
    assert hub.dropped >= 1 and v.dropped >= 1


# ── hysteresis ────────────────────────────────────────────────────────────────

def run_hys(state, seq, *, need_t=3, need_c=2, cooldown=100, start=0, step=1):
    notes = []
    for i, (trig, clr) in enumerate(seq):
        perf.hysteresis(state, trigger=trig, clear=clr, need_trigger=need_t, need_clear=need_c, now=start + i * step,
                        cooldown=cooldown, value=i, message="m", notify=lambda s, w: notes.append(w))
    return notes


def test_alert_needs_consecutive_triggers_and_clears_with_band():
    st = perf.AlertState("k", "system", "T")
    T, F, B = (True, False), (False, True), (False, False)      # trigger / clear / in-between band
    assert run_hys(st, [T, T, F, T, T]) == []                    # never 3 in a row
    st2 = perf.AlertState("k", "system", "T")
    assert run_hys(st2, [T, T, T]) == ["triggered"] and st2.active
    assert run_hys(st2, [B, B, B, B]) == [] and st2.active       # band keeps state
    assert run_hys(st2, [F, B, F]) == [] and st2.active          # clear must be consecutive
    assert run_hys(st2, [F, F]) == ["cleared"] and not st2.active


def test_cooldown_makes_flapping_silent():
    st = perf.AlertState("k", "system", "T")
    seq = [(True, False)] * 3 + [(False, True)] * 2 + [(True, False)] * 3 + [(False, True)] * 2 + [(True, False)] * 3
    notes = run_hys(st, seq, cooldown=100)
    assert notes.count("triggered") == 1                          # re-triggers inside the cooldown are silent
    assert st.active


# ── health classification ─────────────────────────────────────────────────────

TH = perf.THRESHOLD_DEFAULTS


def stream(**kw):
    base = {"state": "streaming", "state_since": 0, "activity": "active", "fps_avg": 24.0, "fps_recent": 24.0, "active_streak": 10,
            "startup_s": 1.2, "last_error": None}
    base.update(kw)
    return base


@pytest.mark.parametrize("kw,expect", [
    (dict(device_state="unauthorized", online=False, stream=None), "authorization_required"),
    (dict(device_state="reconnecting", online=False, stream=None), "reconnecting"),
    (dict(device_state="offline", online=False, stream=None), "disconnected"),
    (dict(device_state="online", online=True, stream=None), "healthy"),
    (dict(device_state="online", online=True, stream=stream()), "healthy"),
    (dict(device_state="online", online=True, stream=stream(fps_recent=2.0)), "degraded"),                 # active but slow
    (dict(device_state="online", online=True, stream=stream(fps_recent=2.0, active_streak=1)), "healthy"),   # brief blip, not sustained
    (dict(device_state="online", online=True, stream=stream(fps_avg=1.0, fps_recent=20.0)), "healthy"),      # old average must not condemn a recovered stream
    (dict(device_state="online", online=True, stream=stream(activity="idle", fps_avg=0.0)), "healthy"),   # idle != broken
    (dict(device_state="online", online=True, stream=stream(state="reconnecting")), "reconnecting"),
    (dict(device_state="online", online=True, stream=stream(state="failed", last_error="boom")), "degraded"),
    (dict(device_state="online", online=True, stream=stream(startup_s=30.0)), "degraded"),
    (dict(device_state="online", online=True, stream=stream(state="starting", state_since=-60)), "degraded"),
    (dict(device_state="online", online=True, stream=stream(state="starting", state_since=-3)), "healthy"),
])
def test_classify_health(kw, expect):
    h, reason = perf.classify_health(now=0, th=TH, recent_reconnects=0, **kw)
    assert h == expect and reason


def test_reconnect_loop_is_degraded_even_if_streaming():
    h, r = perf.classify_health(device_state="online", online=True, stream=stream(), now=0, th=TH, recent_reconnects=6)
    assert h == "degraded" and "reconnect" in r.lower()


# ── downsampling ──────────────────────────────────────────────────────────────

def test_downsample_bounds_points_and_handles_none():
    rows = [{"t": float(i), "sys_cpu": None if i % 3 == 0 else float(i), "reconnects": 1} for i in range(1000)]
    out = perf.downsample(rows, 100)
    assert len(out) <= 100
    assert sum(r["reconnects"] for r in out) == 1000              # reconnect counts are summed, never averaged away
    assert perf.downsample(rows[:10], 100) == rows[:10]
    assert perf.downsample([{"t": 1.0, "sys_cpu": None}] * 500, 10)[0]["sys_cpu"] is None


# ── collector ─────────────────────────────────────────────────────────────────

class FakeHub:
    def __init__(self):
        self.frames = self.bytes = self.dropped = 0
        self.viewers = {1}
        self.width, self.height = 432, 960
        self.first_frame_at = 0.0


class FakeSess:
    def __init__(self, device_id="d1", profile="normal"):
        self.device_id, self.profile = device_id, profile
        self.hub = FakeHub()
        self.state = "streaming"
        self.reconnects = 0
        self.started_at = 1.0
        self.last_error_msg = ""
        self.last_error_wall = 0.0
        self.requested_at = 0.0

    def startup_seconds(self):
        return 1.5 if self.hub.first_frame_at else None


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make_collector(sessions, snap=None, th=None, sysmon=None):
    clk = Clock()
    c = perf.PerfCollector(sessions=lambda: sessions, monitor_snapshot=lambda: snap or {"devices": []},
                           thresholds=lambda: th or {}, clock=clk, sysmon=sysmon or FakeSys([(i * 100, i * 200, i * 100) for i in range(5000)]))
    return c, clk


async def advance(c, clk, n=1, step=2.0, sessions=(), frames=0, nbytes=0):
    for _ in range(n):
        clk.t += step
        for s in sessions:
            s.hub.frames += frames
            s.hub.bytes += nbytes
            if frames and not s.hub.first_frame_at:
                s.hub.first_frame_at = 1.0
        await c.tick()


@pytest.mark.asyncio
async def test_fps_active_vs_idle_are_distinguished():
    s = FakeSess()
    c, clk = make_collector([s])
    await c.tick()
    await advance(c, clk, 4, sessions=[s], frames=48, nbytes=400_000)      # 24 fps, 200 KB/s -> active
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["activity"] == "active" and 23 <= row["fps"] <= 25 and row["health"] == "healthy"
    assert c.last_sample["fps_avg"] is not None
    await advance(c, clk, 20, sessions=[s], frames=0, nbytes=0)            # static screen: no data at all
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["activity"] == "idle" and row["health"] == "healthy"        # idle is NOT a failure
    assert c.last_sample["fps_avg"] is None                                 # chart gets a gap, not a fake 0


@pytest.mark.asyncio
async def test_slow_active_stream_is_degraded():
    s = FakeSess()
    c, clk = make_collector([s])
    await c.tick()
    await advance(c, clk, 20, sessions=[s], frames=4, nbytes=60_000)       # 2 fps with 30 KB/s: active but slow
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "usb", "state": "online", "is_online": True}])[0]
    assert row["activity"] == "active" and row["health"] == "degraded" and "FPS rendah" in row["health_reason"]


@pytest.mark.asyncio
async def test_rows_report_na_with_reasons():
    c, clk = make_collector([])
    await c.tick()
    row = c.device_rows([{"device_id": "x", "name": "N", "transport": None, "state": "offline", "is_online": False}])[0]
    assert row["fps"] is None and "fps" in row["na"] and "Tiada strim" in row["na"]["fps"]
    assert "client" in row["na"] and "storage" in row["na"]
    assert row["health"] == "disconnected" and row["battery"] is None


@pytest.mark.asyncio
async def test_reconnect_counts_and_loop_alert():
    s = FakeSess()
    c, clk = make_collector([s], th={"perf_reconnect_loop_count": 3})
    await c.tick()
    for _ in range(4):
        s.reconnects += 1
        await advance(c, clk, 1)
    await advance(c, clk, 3)
    assert c._reconnect_total == 4
    assert any(a["key"] == "reconnect_loop" and a["scope"] == "d1" for a in c.active_alerts())
    ov = c.overview(c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}]))
    assert ov["reconnects"]["5m"] == 4 and ov["health"]["status"] == "degraded"
    # quiet period beyond the window clears it
    await advance(c, clk, 80, step=2.0)
    assert not any(a["key"] == "reconnect_loop" for a in c.active_alerts())
    assert any(e["kind"] == "alert" for e in perf_events.recent(50))


@pytest.mark.asyncio
async def test_stalled_failed_stream_alert():
    s = FakeSess()
    s.state = "failed"
    c, clk = make_collector([s])
    await c.tick()
    await advance(c, clk, 3)
    assert any(a["key"] == "stream_stalled" for a in c.active_alerts())
    s.state = "streaming"
    await advance(c, clk, 4)
    assert not any(a["key"] == "stream_stalled" for a in c.active_alerts())


@pytest.mark.asyncio
async def test_high_ram_alert_with_hysteresis():
    c, clk = make_collector([], sysmon=FakeSys([(i, i * 2, i) for i in range(500)], mem=(15500.0, 16000.0)))   # 96.9 %
    await c.tick()
    await advance(c, clk, 5)
    assert any(a["key"] == "ram_high" for a in c.active_alerts())
    c._sys._mem = (14700.0, 16000.0)             # 91.9 %: still above (90-5)=85 -> stays active (band)
    await advance(c, clk, 8)
    assert any(a["key"] == "ram_high" for a in c.active_alerts())
    c._sys._mem = (8000.0, 16000.0)
    await advance(c, clk, 8)
    assert not any(a["key"] == "ram_high" for a in c.active_alerts())


@pytest.mark.asyncio
async def test_too_many_streams_alert_and_sustained_cpu():
    ss_ = [FakeSess(f"d{i}") for i in range(10)]
    # CPU 100 % busy: idle never advances
    times = [(0, i * 100, 0) for i in range(2000)]
    c, clk = make_collector(ss_, th={"perf_cpu_sustain_s": 10}, sysmon=FakeSys([(0, 0, 0)] + [(0, i * 100, i * 100) for i in range(1, 2000)]))
    await c.tick()
    await advance(c, clk, 8)
    keys = {a["key"] for a in c.active_alerts()}
    assert "too_many_streams" in keys and "cpu_high" in keys and times


@pytest.mark.asyncio
async def test_memory_growth_alert(monkeypatch):
    c, clk = make_collector([], th={"perf_rss_growth_mb": 100})
    rss = {"v": 200.0}
    monkeypatch.setattr(perf, "process_metrics", lambda: {"rss_mb": rss["v"], "threads": 5, "handles": 100})
    await c.tick()
    for i in range(400):                           # 400 ticks x 2 s = 800 s of steady growth (0.5 MB/tick = 200 MB)
        rss["v"] += 0.5
        await advance(c, clk, 1)
    assert any(a["key"] == "memory_growth" for a in c.active_alerts())


@pytest.mark.asyncio
async def test_flat_memory_never_alerts(monkeypatch):
    c, clk = make_collector([])
    monkeypatch.setattr(perf, "process_metrics", lambda: {"rss_mb": 200.0, "threads": 5, "handles": 100})
    await c.tick()
    await advance(c, clk, 400)
    assert not any(a["key"] == "memory_growth" for a in c.active_alerts())


@pytest.mark.asyncio
async def test_retention_is_bounded():
    c, clk = make_collector([])
    await c.tick()
    await advance(c, clk, perf.FINE_MAX + 300, step=2.0)
    assert len(c.fine) == perf.FINE_MAX
    assert len(c.coarse) <= perf.COARSE_MAX and len(c.coarse) > 100
    assert len(c.history("1h", 240)) <= 240 and len(c.history("session", 240)) <= 240
    assert len(c.history("5m", 240)) <= 150 + 1


@pytest.mark.asyncio
async def test_sessions_that_disappear_are_forgotten():
    s = FakeSess()
    sessions = [s]
    c, clk = make_collector(sessions)
    await c.tick()
    await advance(c, clk, 2, sessions=[s], frames=10, nbytes=1000)
    assert c._prev_counters
    sessions.clear()
    await advance(c, clk, 1)
    assert not c._prev_counters and not c._rates and not c._fps_hist


def test_ws_gauge_is_balanced_even_on_error():
    with pytest.raises(RuntimeError):
        with perf.track_ws("video"):
            assert perf.ws_snapshot()["video"] == 1
            raise RuntimeError("x")
    assert perf.ws_snapshot()["video"] == 0
    with perf.track_ws("a"), perf.track_ws("a"):
        assert perf.ws_snapshot()["a"] == 2
    assert perf.ws_snapshot()["a"] == 0


@pytest.mark.asyncio
async def test_client_stats_shown_when_fresh_and_bounded():
    s = FakeSess()
    c, clk = make_collector([s])
    await c.tick()
    c.report_client("d1", "normal", received=100, decoded=98, dropped=2, fps=24.0, width=432, height=960)
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["client"]["decoded"] == 98 and "client" not in row["na"]
    clk.t += 60
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["client"] is None and "client" in row["na"]           # stale report -> N/A
    for i in range(1000):
        c.report_client(f"id{i}", "thumb", received=1, decoded=1, dropped=0, fps=1.0, width=1, height=1)
    assert len(c.client_stats) <= 257


# ── report / redaction ────────────────────────────────────────────────────────

def test_redact_masks_ip_secrets_paths_serials():
    t = "connect 192.168.1.112:36073 failed key sk-abcdef1234567890 at C:\\Users\\addy RVSBD\\x\\y adb-1C201FDF600DZW-WnZDb6._adb-tls-connect._tcp password=hunter2"
    r = perf_report.redact(t)
    assert "192.168.1.112" not in r and "192.168.x.x" in r
    assert "sk-abcdef" not in r and "hunter2" not in r
    assert "addy RVSBD" not in r and "<user>" in r
    assert "1C201FDF600DZW" not in r
    assert perf_report.redact(None) is None
    assert perf_report.mask_serial("ABCDEF1234567890") == "ABCD…90" and perf_report.mask_serial("abc") == "***"


@pytest.mark.asyncio
async def test_report_has_no_secrets_and_summaries(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRETSECRETSECRET1234")
    s = FakeSess("d1abcdef0123")
    s.last_error_msg = "timed out connecting 10.1.2.3:5555 for C:\\Users\\bob\\AppData"
    c, clk = make_collector([s])
    await c.tick()
    perf_events.emit("device", "gone 192.168.5.6:5555", device_id="d1")
    rows = c.device_rows([{"device_id": "d1abcdef0123", "name": "Pixel", "transport": "wifi", "state": "online", "is_online": True,
                           "last_error": ""}])
    rep = perf_report.build_report(c, rows, {"version": "adb 1.0.41", "ok": True, "error": ""}, [{"id": "x", "title": "t", "status": "PASS", "detail": "C:\\Users\\bob\\x", "hint": ""}])
    import json
    blob = json.dumps(rep)
    assert "SECRETSECRET" not in blob and "10.1.2.3" not in blob and "192.168.5.6" not in blob and "bob" not in blob
    assert rep["devices"][0]["device_id"].endswith("…") and rep["summary"] and rep["identifiers_included"] is False
    assert "Pixel" in perf_report.to_text(rep)
    full = perf_report.build_report(c, rows, {"version": "v", "ok": True, "error": ""}, [], include_identifiers=True)
    assert "10.1.2.3" in json.dumps(full)                                   # only when explicitly requested


def test_explain_gives_plain_language_for_each_state():
    base = {"name": "P", "health_reason": "r"}
    for h in ("authorization_required", "disconnected", "reconnecting", "healthy"):
        assert "P" in perf_report.explain({**base, "health": h})
    assert "kabel" in perf_report.explain({**base, "health": "degraded", "health_reason": "5 sambungan semula (gelung reconnect)"})
    assert "Security settings" in perf_report.explain({**base, "health": "degraded", "health_reason": "Strim gagal: x"})


def test_csv_exports_have_headers_and_blanks_for_na():
    h = perf_report.history_csv([{"t": 1700000000.0, "sys_cpu": None, "sys_ram_pct": 40.0, "streams": 1, "fps_avg": None, "reconnects": 0}])
    lines = h.strip().splitlines()
    assert lines[0].startswith("time_utc,sys_cpu") and ",40.0," in lines[1] and lines[1].count(",") == lines[0].count(",")
    d = perf_report.devices_csv([{"device_id": "a", "name": "n", "fps": None}])
    assert d.splitlines()[0].startswith("device_id,name") and "a,n," in d
    e = perf_report.events_csv([{"time": "t", "kind": "k", "level": "info", "device_id": None, "message": "m, with comma"}])
    assert '"m, with comma"' in e


@pytest.mark.asyncio
async def test_start_up_keyframe_burst_is_never_judged_as_slow_activity(monkeypatch):
    """Real-hardware finding: the initial GOP burst made an idle phone look 'active but 0.4 fps' (false degraded)."""
    import time as _t
    s = FakeSess()
    c, clk = make_collector([s])
    await c.tick()
    s.hub.first_frame_at = _t.monotonic()            # stream just started
    await advance(c, clk, 1, sessions=[s], frames=40, nbytes=300_000)       # keyframe burst
    await advance(c, clk, 3, sessions=[s], frames=1, nbytes=1_000)          # then a static screen
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["activity"] == "warmup" and row["health"] == "healthy"
    s.hub.first_frame_at = _t.monotonic() - 60                              # past warm-up, still static
    await advance(c, clk, 4, sessions=[s], frames=0, nbytes=0)
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["activity"] == "idle" and row["health"] == "healthy"
    assert c.last_sample["fps_avg"] is None


@pytest.mark.asyncio
async def test_tiny_periodic_updates_are_idle_not_slow():
    s = FakeSess()
    c, clk = make_collector([s])
    await c.tick()
    await advance(c, clk, 30, sessions=[s], frames=2, nbytes=4_000)         # ~1 fps, 2 KB/s: clock tick / cursor blink
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["activity"] == "idle" and row["health"] == "healthy"


@pytest.mark.asyncio
async def test_brief_activity_blip_after_idle_is_not_degraded():
    """Real-hardware finding: a short notification animation on an idle phone flipped it to 'degraded' for one sample."""
    s = FakeSess()
    c, clk = make_collector([s])
    await c.tick()
    await advance(c, clk, 20, sessions=[s], frames=0, nbytes=0)             # idle
    await advance(c, clk, 1, sessions=[s], frames=11, nbytes=80_000)        # 5 fps blip, 40 KB/s
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["health"] == "healthy"


@pytest.mark.asyncio
async def test_device_names_that_are_addresses_are_masked_in_the_report():
    """Real finding: legacy devices are named after their IP:port; the exported summary leaked it."""
    c, clk = make_collector([])
    await c.tick()
    rows = c.device_rows([{"device_id": "abcdef012345", "name": "192.168.1.109:32771", "transport": "wifi", "state": "offline",
                           "is_online": False, "last_error": "x"}])
    import json
    rep = perf_report.build_report(c, rows, {"version": "v", "ok": True, "error": ""}, [])
    blob = json.dumps(rep)
    assert "192.168.1.109" not in blob and "192.168.x.x" in blob
    full = json.dumps(perf_report.build_report(c, rows, {"version": "v", "ok": True, "error": ""}, [], include_identifiers=True))
    assert "192.168.1.109" in full


@pytest.mark.asyncio
async def test_device_reconnect_total_survives_session_replacement():
    s = FakeSess()
    sessions = [s]
    c, clk = make_collector(sessions)
    await c.tick()
    s.reconnects = 2
    await advance(c, clk, 1)
    sessions[:] = [FakeSess()]               # transport changed -> a brand new session object with a zero counter
    await advance(c, clk, 2)
    row = c.device_rows([{"device_id": "d1", "name": "P", "transport": "wifi", "state": "online", "is_online": True}])[0]
    assert row["reconnects"] == 2
