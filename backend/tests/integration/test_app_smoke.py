"""
Full application smoke test: real `app.main:app`, real lifespan, real SQLite file in a temp data dir.
adb is replaced by a scripted fake so no phone / adb.exe is needed.
"""
import sqlite3

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import runtime_paths as rp
from app.services import adb_client
from app.services.adb_client import AdbDevice

OK = {"Origin": "http://127.0.0.1:8000", "Host": "127.0.0.1:8000"}   # WS TestClient ignores base_url for Host
BAD = {"Origin": "http://evil.example", "Host": "127.0.0.1:8000"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRRORHUB_DATA_DIR", str(tmp_path / "data"))
    # fresh module-level singletons that cache paths / sessions
    import app.devices.lifecycle as lc
    monkeypatch.setattr(lc, "_monitor", None)

    async def no_devices():
        return []

    async def start():
        return None

    monkeypatch.setattr(adb_client, "list_devices", no_devices)
    monkeypatch.setattr(adb_client, "start_server", start)
    # the engine in app.models.database was created at import time with whatever data dir existed then;
    # point it at the temp DB for this test
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    import app.models.database as dbm
    eng = create_async_engine(rp.sqlite_url())
    monkeypatch.setattr(dbm, "engine", eng)
    monkeypatch.setattr(dbm, "AsyncSessionLocal", async_sessionmaker(eng, expire_on_commit=False))
    import app.migration as mig
    monkeypatch.setattr(mig, "DB_PATH", rp.db_path())
    # Legacy background loops (campaign dispatcher, orchestrator monitor, AI agents) are out of V1 scope and
    # may block loop shutdown on adb calls; replace them with idle coroutines here.
    import asyncio

    async def idle(*a, **k):
        await asyncio.sleep(3600)

    import app.campaign.dispatcher as disp
    import app.orchestrator.monitor as omon
    import app.agents.manager as amgr
    monkeypatch.setattr(disp, "run_loop", idle)
    monkeypatch.setattr(omon, "run_monitor", idle)
    monkeypatch.setattr(amgr, "run_loop", idle)
    from app.main import app
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


def test_health_and_about(client):
    assert client.get("/health").json() == {"status": "ok", "app": "MirrorHub"}
    j = client.get("/api/v1/system/about").json()
    assert j["version"] and j["database"]["path"].endswith("mirrorhub.db")


def test_data_dir_is_appdata_style_not_install_dir(client):
    j = client.get("/api/v1/system/data").json()
    assert j["data_dir"] == str(rp.data_dir()) and j["database"] == str(rp.db_path())
    assert rp.db_path().exists()


def test_diagnostics_endpoint_shape(client):
    j = client.get("/api/v1/system/diagnostics").json()
    assert j["overall"] in {"PASS", "WARN", "FAIL"}
    ids = {c["id"] for c in j["checks"]}
    assert {"os", "data_dir", "disk", "scrcpy_server"} <= ids
    assert all(c["status"] in {"PASS", "WARN", "FAIL", "INFO"} for c in j["checks"])


def test_backup_and_staged_restore_via_api(client):
    r = client.post("/api/v1/system/backup")
    assert r.status_code == 200
    name = r.json()["name"]
    assert name in [b["name"] for b in client.get("/api/v1/system/data").json()["backups"]]
    r = client.post(f"/api/v1/system/restore/{name}")
    assert r.status_code == 200 and "buka semula" in r.json()["message"]
    assert (rp.data_dir() / "restore.pending.json").exists()
    assert client.post("/api/v1/system/restore/..%2Fevil.db").status_code in (400, 404, 405)  # decoded slash never reaches the handler
    assert client.post("/api/v1/system/restore/notthere.db").status_code == 400


def test_foreign_origin_rejected_on_real_app(client):
    r = client.post("/api/v1/pairing/refresh", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert client.post("/api/v1/pairing/refresh", headers=OK).status_code == 200


def test_host_header_rebinding_rejected(client):
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 403


def test_spa_fallback_and_static(client):
    dist = rp.frontend_dist()
    if not (dist / "index.html").exists():
        pytest.skip("frontend not built")
    assert b'<div id="root">' in client.get("/pairing").content            # React Router deep link
    assert client.get("/device/anything").status_code == 200


def test_devices_websocket_sends_snapshot_and_rejects_bad_origin(client):
    with client.websocket_connect("/ws/devices", headers=OK) as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and snap["adb_ok"] is True and snap["devices"] == []
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/devices", headers=BAD):
            pass


def test_video_ws_unknown_device_closes_with_4404(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws/video/nope?profile=normal", headers=OK) as ws:
            assert "not found" in ws.receive_json()["error"]
            ws.receive_text()
    assert e.value.code == 4404


def test_video_ws_bad_profile_closes_with_4400(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws/video/nope?profile=huge", headers=OK) as ws:
            assert "unknown profile" in ws.receive_json()["error"]
            ws.receive_text()
    assert e.value.code == 4400


def test_control_ws_rejects_mismatched_device_and_bad_payload(client, monkeypatch):
    # register a device row directly, then drive the control socket
    from app.devices.lifecycle import new_device_id
    did = new_device_id("SER9", None)
    con = sqlite3.connect(str(rp.db_path()))
    con.execute("INSERT INTO devices (device_id, device_name, battery, wifi, is_online, adb_address, last_seen, created_at) "
                "VALUES (?,?,?,?,?,?,datetime('now'),datetime('now'))", (did, "T", 50, 1, 1, "SER9"))
    con.commit()
    con.close()
    sent = []
    from app.services import adb_control

    def real_validation_fake_send(addr, x, y):          # keep the real validate_rel() path: patch only the actuator
        adb_control.validate_rel(x)
        adb_control.validate_rel(y)
        sent.append((addr, x, y))

    monkeypatch.setattr(adb_control, "tap", real_validation_fake_send)
    with client.websocket_connect(f"/ws/control/{did}", headers=OK) as ws:
        ws.send_json({"type": "tap", "x": 0.5, "y": 0.5, "device_id": "someone-else"})
        assert ws.receive_json()["error"]
        ws.send_json({"type": "tap", "x": 0.5, "y": 0.5, "device_id": did})
        ws.send_json({"type": "tap", "x": 7, "y": 0.5})
        err = ws.receive_json()
        assert err["error"] == "invalid_command" and "within 0..1" in err["detail"]
    assert sent == [("SER9", 0.5, 0.5)]            # only the valid, correctly bound command reached the phone's adb address


def test_forget_and_patch_roundtrip_on_real_db(client):
    con = sqlite3.connect(str(rp.db_path()))
    con.execute("INSERT INTO devices (device_id, device_name, battery, wifi, is_online, adb_address, last_seen, created_at) "
                "VALUES ('dx','X',1,1,0,'1.2.3.4:5555',datetime('now'),datetime('now'))")
    con.commit()
    con.close()
    r = client.patch("/api/v1/devices/dx", json={"device_name": "Renamed", "tags": ["a"]})
    assert r.status_code == 200 and r.json()["device_name"] == "Renamed"
    assert client.get("/api/v1/devices/dx").json()["tags"] == ["a"]
    assert client.delete("/api/v1/devices/dx?confirm=true").status_code == 200
    assert client.get("/api/v1/devices/dx").status_code == 404


def test_control_ws_reports_blocked_input_on_connect(client, monkeypatch):
    from app.devices.lifecycle import new_device_id
    from app.services import device_ops
    did = new_device_id("SERB", None)
    con = sqlite3.connect(str(rp.db_path()))
    con.execute("INSERT INTO devices (device_id, device_name, battery, wifi, is_online, adb_address, last_seen, created_at) "
                "VALUES (?,?,?,?,?,?,datetime('now'),datetime('now'))", (did, "B", 50, 1, 1, "SERB"))
    con.commit()
    con.close()

    async def blocked(serial):
        return "blocked", device_ops.INPUT_BLOCKED_MSG

    monkeypatch.setattr(device_ops, "input_state", blocked)
    with client.websocket_connect(f"/ws/control/{did}", headers=OK) as ws:
        msg = ws.receive_json()
    assert msg["error"] == "input_blocked" and "Security settings" in msg["detail"]


def test_preferences_api_roundtrip_and_validation(client):
    assert client.get("/api/v1/system/preferences").json()["auto_reconnect"] is True
    r = client.put("/api/v1/system/preferences", json={"wall_layout": 4, "record_seconds": 20})
    assert r.status_code == 200 and r.json()["wall_layout"] == 4
    assert client.get("/api/v1/system/preferences").json()["record_seconds"] == 20
    assert client.put("/api/v1/system/preferences", json={"wall_layout": 7}).status_code == 400
    assert client.put("/api/v1/system/preferences", json={"bogus": 1}).status_code == 400
    assert client.get("/api/v1/system/preferences").json()["wall_layout"] == 4      # failed update changed nothing


# ── Performance dashboard API ─────────────────────────────────────────────────

def test_perf_overview_history_devices_events(client):
    import time
    ov = client.get("/api/v1/perf/overview").json()
    assert {"devices", "pc", "process", "health", "reconnects", "ws", "thresholds", "alerts"} <= set(ov)
    assert ov["health"]["status"] in ("healthy", "degraded") and ov["fps_avg"] is None and "N/A" in ov["fps_note"]
    assert ov["process"]["rss_mb"] is None or ov["process"]["rss_mb"] > 0
    assert "Mirrorhub" in ov["process"]["note"]
    for rng in ("5m", "15m", "1h", "session"):
        h = client.get(f"/api/v1/perf/history?range={rng}").json()
        assert h["range"] == rng and isinstance(h["points"], list) and len(h["points"]) <= 240
    assert client.get("/api/v1/perf/history?range=forever").status_code == 422
    assert isinstance(client.get("/api/v1/perf/devices").json(), list)      # dev checkouts migrate a legacy DB into the temp dir
    assert isinstance(client.get("/api/v1/perf/events").json(), list)
    assert client.get("/api/v1/perf/events?limit=0").status_code == 422
    a = client.get("/api/v1/perf/alerts").json()
    assert "active" in a and "history" in a and time


def test_perf_thresholds_validate_and_persist(client):
    th = client.get("/api/v1/perf/thresholds").json()
    assert th["perf_ram_high_pct"] == 90 and "defaults" in th
    assert client.put("/api/v1/perf/thresholds", json={"perf_ram_high_pct": 80}).json()["perf_ram_high_pct"] == 80
    assert client.get("/api/v1/perf/overview").json()["thresholds"]["perf_ram_high_pct"] == 80
    assert client.put("/api/v1/perf/thresholds", json={"perf_ram_high_pct": 5}).status_code == 400
    assert client.put("/api/v1/perf/thresholds", json={"wall_layout": 4}).status_code == 400     # only perf_* keys here
    assert client.put("/api/v1/perf/thresholds", json={"nope": 1}).status_code == 400


def test_perf_device_table_for_registered_offline_device(client):
    con = sqlite3.connect(str(rp.db_path()))
    con.execute("INSERT INTO devices (device_id, device_name, battery, wifi, is_online, adb_address, last_seen, created_at, state, transport) "
                "VALUES ('pd1','Offline Phone',50,1,0,'1.2.3.4:5555',datetime('now'),datetime('now'),'offline','wifi')")
    con.commit()
    con.close()
    rows = client.get("/api/v1/perf/devices").json()
    r = next(x for x in rows if x["device_id"] == "pd1")
    assert r["health"] == "disconnected" and r["fps"] is None and "fps" in r["na"] and r["transport"] == "wifi"
    ov = client.get("/api/v1/perf/overview").json()
    assert ov["devices"]["disconnected"] >= 1


def test_perf_client_stats_validation(client):
    ok = {"device_id": "pd1", "profile": "normal", "received": 10, "decoded": 9, "dropped": 1, "fps": 24.0, "width": 432, "height": 960}
    assert client.post("/api/v1/perf/client-stats", json=ok).status_code == 200
    assert client.post("/api/v1/perf/client-stats", json={**ok, "received": -1}).status_code == 422
    assert client.post("/api/v1/perf/client-stats", json={**ok, "fps": 99999}).status_code == 422
    assert client.post("/api/v1/perf/client-stats", json={"device_id": "x" * 200}).status_code == 422


def test_perf_diagnostics_export_has_no_secrets_and_valid_shapes(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-LEAKCHECK1234567890abcd")
    from app.services import perf_events
    perf_events.emit("error", r"boom at 192.168.77.5:5555 in C:\Users\someone\AppData key=sk-LEAKCHECK1234567890abcd")
    j = client.get("/api/v1/perf/diagnostics")
    assert j.status_code == 200
    blob = j.text
    assert "LEAKCHECK" not in blob and "192.168.77.5" not in blob and "someone" not in blob
    rep = j.json()
    assert rep["report"] == "mirrorhub-diagnostics" and rep["identifiers_included"] is False
    assert {"overview", "thresholds", "devices", "events", "environment_checks", "summary", "system", "app"} <= set(rep)
    txt = client.get("/api/v1/perf/diagnostics.txt")
    assert txt.status_code == 200 and "Mirrorhub diagnostic report" in txt.text and "LEAKCHECK" not in txt.text
    for kind in ("history", "devices", "events"):
        r = client.get(f"/api/v1/perf/export.csv?kind={kind}")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "LEAKCHECK" not in r.text
        assert f"mirrorhub_{kind}.csv" in r.headers["content-disposition"]
    assert client.get("/api/v1/perf/export.csv?kind=secrets").status_code == 422
