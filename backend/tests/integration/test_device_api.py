"""
HTTP-level tests for pairing, device manager, APK and file APIs.
Routers are mounted in a small app with an in-memory DB; adb is faked.
"""
import io
import zipfile

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import apps_files, device_manager, pairing
from app.api.devices import router as devices_router
from app.core import runtime_paths as rp
from app.devices.lifecycle import DeviceMonitor
from app.models.database import get_db
from app.models.device import Device
from app.services import adb_client, device_ops
from app.services.adb_client import AdbDevice, AdbError, AdbResult


@pytest_asyncio.fixture()
async def env(db_engine, monkeypatch, tmp_path):
    monkeypatch.setenv("MIRRORHUB_DATA_DIR", str(tmp_path / "data"))
    sf = async_sessionmaker(db_engine, expire_on_commit=False)
    app = FastAPI()
    for r in (devices_router, device_manager.router, pairing.router, apps_files.apps_router, apps_files.files_router):
        app.include_router(r, prefix="/api/v1")

    async def _db():
        async with sf() as s:
            yield s

    app.dependency_overrides[get_db] = _db

    async def _no_devices():
        return []

    async def _same(serial, hw):
        return serial

    mon = DeviceMonitor(session_factory=sf, lister=_no_devices, info_fetcher=None or (lambda s: None), resolver=_same)
    monkeypatch.setattr("app.devices.lifecycle._monitor", mon)

    async with sf() as s:
        s.add(Device(device_id="d1", device_name="Pixel", adb_address="SER1", is_online=True, state="online"))
        s.add(Device(device_id="off", device_name="Offline", adb_address="SER2", is_online=False, state="offline",
                     last_error="Sambungan terputus."))
        s.add(Device(device_id="wifi", device_name="W", adb_address="192.168.1.9:5555", is_online=True))
        await s.commit()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as c:
        yield c, sf, mon


def fake_run(monkeypatch, handler):
    async def run(*args, serial=None, timeout=15, **kw):
        return handler(args, serial)
    monkeypatch.setattr(device_ops, "run_adb", run)
    monkeypatch.setattr(adb_client, "run_adb", run)


# ── devices / manager ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_includes_manager_fields(env):
    c, *_ = env
    r = await c.get("/api/v1/devices")
    assert r.status_code == 200
    d = {x["device_id"]: x for x in r.json()}
    assert d["d1"]["state"] == "online" and d["d1"]["tags"] == [] and "storage_free_mb" in d["d1"]


@pytest.mark.asyncio
async def test_patch_rename_tags_group(env):
    c, *_ = env
    r = await c.patch("/api/v1/devices/d1", json={"device_name": "  Farm 01 ", "tags": ["tiktok", "a", "a", " "],
                                                  "group_name": "Rak A", "notes": "n"})
    j = r.json()
    assert r.status_code == 200 and j["device_name"] == "Farm 01" and j["tags"] == ["a", "tiktok"]
    assert j["group_name"] == "Rak A" and j["notes"] == "n"
    assert (await c.patch("/api/v1/devices/d1", json={"device_name": "   "})).status_code == 400
    assert (await c.patch("/api/v1/devices/nope", json={"device_name": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_forget_requires_confirm_and_only_removes_row(env):
    c, sf, _ = env
    assert (await c.delete("/api/v1/devices/d1")).status_code == 400
    assert (await c.get("/api/v1/devices/d1")).status_code == 200
    r = await c.delete("/api/v1/devices/d1?confirm=true")
    assert r.status_code == 200 and (await c.get("/api/v1/devices/d1")).status_code == 404


@pytest.mark.asyncio
async def test_offline_device_operations_give_conflict_with_reason(env):
    c, *_ = env
    r = await c.post("/api/v1/devices/off/screenshot")
    assert r.status_code == 409 and "offline" in r.json()["detail"].lower() and "terputus" in r.json()["detail"]
    assert (await c.get("/api/v1/files/off/list")).status_code == 409
    assert (await c.get("/api/v1/apps/off/packages")).status_code == 409


@pytest.mark.asyncio
async def test_screenshot_png(env, monkeypatch):
    c, *_ = env

    async def shot(serial):
        assert serial == "SER1"
        return device_ops.PNG_MAGIC + b"x"

    monkeypatch.setattr(device_ops, "screenshot", shot)
    r = await c.post("/api/v1/devices/d1/screenshot")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(device_ops.PNG_MAGIC)

    async def boom(serial):
        raise AdbError("Skrin tidak dapat ditangkap")

    monkeypatch.setattr(device_ops, "screenshot", boom)
    r = await c.post("/api/v1/devices/d1/screenshot")
    assert r.status_code == 502 and "tidak dapat" in r.json()["detail"]


@pytest.mark.asyncio
async def test_reconnect_only_for_wifi(env, monkeypatch):
    c, _, mon = env
    assert (await c.post("/api/v1/devices/d1/reconnect")).status_code == 400   # USB serial
    called = []

    async def conn(addr):
        called.append(addr)
        return True, "connected to"

    mon._connect = conn
    r = await c.post("/api/v1/devices/wifi/reconnect")
    assert r.status_code == 200 and r.json()["ok"] and called == ["192.168.1.9:5555"]


@pytest.mark.asyncio
async def test_disconnect_suppresses_auto_reconnect(env, monkeypatch):
    c, _, mon = env

    async def disc(addr):
        return True, "disconnected"

    monkeypatch.setattr(adb_client, "disconnect", disc)
    assert (await c.post("/api/v1/devices/wifi/disconnect")).json()["ok"]
    assert "192.168.1.9:5555" in mon._suppress


@pytest.mark.asyncio
async def test_recording_name_validation(env):
    c, *_ = env
    assert (await c.get("/api/v1/recordings/..%2Fx.mp4")).status_code in (400, 404)
    assert (await c.get("/api/v1/recordings/missing.mp4")).status_code == 404
    (rp.data_dir() / "recordings").mkdir(exist_ok=True)
    (rp.data_dir() / "recordings" / "ok.mp4").write_bytes(b"mp4")
    assert (await c.get("/api/v1/recordings/ok.mp4")).content == b"mp4"
    assert (await c.get("/api/v1/recordings/a.txt")).status_code == 400


# ── pairing ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pair_endpoint_validation_and_result(env, monkeypatch):
    c, *_ = env
    r = await c.post("/api/v1/pairing/wifi/pair", json={"address": "bad", "code": "123456"})
    assert r.status_code == 502 or r.status_code == 400
    seen = []

    def handler(args, serial):
        seen.append(args)
        return AdbResult(0, "Successfully paired to 1.2.3.4:4000 [guid=x]")

    fake_run(monkeypatch, handler)
    r = await c.post("/api/v1/pairing/wifi/pair", json={"address": "1.2.3.4:4000", "code": "123456"})
    assert r.json() == {"ok": True, "message": "Pairing berjaya."}
    assert seen == [("pair", "1.2.3.4:4000", "123456")]
    r = await c.post("/api/v1/pairing/wifi/pair", json={"address": "1.2.3.4:4000", "code": "12"})
    assert r.status_code in (400, 502) and len(seen) == 1


@pytest.mark.asyncio
async def test_connect_failure_message_is_actionable(env, monkeypatch):
    c, *_ = env
    fake_run(monkeypatch, lambda a, s: AdbResult(0, "failed to connect to '1.2.3.4:5555': Connection refused"))
    r = await c.post("/api/v1/pairing/wifi/connect", json={"address": "1.2.3.4:5555"})
    assert r.json()["ok"] is False and "port" in r.json()["message"].lower()


@pytest.mark.asyncio
async def test_connect_success_triggers_monitor_tick(env, monkeypatch):
    c, _, mon = env
    fake_run(monkeypatch, lambda a, s: AdbResult(0, "connected to 1.2.3.4:5555"))
    ticks = []

    async def tick():
        ticks.append(1)

    mon.tick = tick
    assert (await c.post("/api/v1/pairing/wifi/connect", json={"address": "1.2.3.4:5555"})).json()["ok"]
    assert ticks == [1]


@pytest.mark.asyncio
async def test_discover_lists_mdns(env, monkeypatch):
    c, *_ = env
    fake_run(monkeypatch, lambda a, s: AdbResult(0, "x\t_adb-tls-pairing._tcp\t192.168.1.5:41000\n"))
    j = (await c.get("/api/v1/pairing/wifi/discover")).json()
    assert j["services"] == [{"name": "x", "kind": "pairing", "address": "192.168.1.5:41000"}]


@pytest.mark.asyncio
async def test_pairing_status_marks_registered(env, monkeypatch):
    c, *_ = env

    def handler(args, serial):
        if args[0] == "version":
            return AdbResult(0, "Android Debug Bridge version 1.0.41\n")
        return AdbResult(0, "List of devices attached\nSER1\tdevice model:Pixel\nNEW9\tunauthorized\n")

    fake_run(monkeypatch, handler)
    j = (await c.get("/api/v1/pairing/status")).json()
    by = {d["serial"]: d for d in j["devices"]}
    assert by["SER1"]["registered"] and by["SER1"]["device_id"] == "d1"
    assert not by["NEW9"]["registered"] and by["NEW9"]["state"] == "unauthorized"


@pytest.mark.asyncio
async def test_adb_missing_is_503(env, monkeypatch):
    c, *_ = env

    async def missing(*a, **k):
        raise adb_client.AdbMissing("adb.exe tidak dijumpai")

    monkeypatch.setattr(adb_client, "run_adb", missing)
    r = await c.get("/api/v1/pairing/wifi/discover")
    assert r.status_code == 503 and "adb.exe" in r.json()["detail"]


# ── APK ───────────────────────────────────────────────────────────────────────

def make_apk_bytes() -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("AndroidManifest.xml", "x")
    return b.getvalue()


@pytest.mark.asyncio
async def test_apk_library_upload_validation_delete(env):
    c, *_ = env
    r = await c.post("/api/v1/apps/apks", files={"file": ("my app.apk", make_apk_bytes())})
    assert r.status_code == 200 and r.json()["name"] == "my app.apk"
    assert (await c.post("/api/v1/apps/apks", files={"file": ("evil.exe", b"MZ")})).status_code == 400
    assert (await c.post("/api/v1/apps/apks", files={"file": ("fake.apk", b"not a zip at all")})).status_code == 400
    names = [a["name"] for a in (await c.get("/api/v1/apps/apks")).json()]
    assert names == ["my app.apk"]
    assert not list((rp.data_dir() / "apks").glob("*.part"))                   # no temp leftovers
    r = await c.post("/api/v1/apps/apks", files={"file": ("../../x.apk", make_apk_bytes())})
    assert r.status_code == 200 and r.json()["name"] == "x.apk"                # path stripped, stays in library
    assert (await c.delete("/api/v1/apps/apks/my app.apk")).status_code == 200
    assert (await c.delete("/api/v1/apps/apks/my app.apk")).status_code == 404
    assert (await c.delete("/api/v1/apps/apks/..%2Fa.apk")).status_code in (400, 404)


@pytest.mark.asyncio
async def test_install_single_and_errors(env, monkeypatch):
    c, *_ = env
    await c.post("/api/v1/apps/apks", files={"file": ("a.apk", make_apk_bytes())})
    calls = []

    def handler(args, serial):
        calls.append((args, serial))
        return AdbResult(0, "Success")

    fake_run(monkeypatch, handler)
    r = await c.post("/api/v1/apps/d1/install", json={"apk": "a.apk"})
    assert r.json()["ok"] and calls[0][1] == "SER1" and calls[0][0][:3] == ("install", "-r", "-g")
    assert (await c.post("/api/v1/apps/d1/install", json={"apk": "missing.apk"})).status_code == 400
    assert (await c.post("/api/v1/apps/d1/install", json={"apk": "../a.apk"})).status_code == 400
    fake_run(monkeypatch, lambda a, s: AdbResult(1, "Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]"))
    r = await c.post("/api/v1/apps/d1/install", json={"apk": "a.apk"})
    assert r.json()["ok"] is False and "storan" in r.json()["message"]


@pytest.mark.asyncio
async def test_install_many_isolates_failures(env, monkeypatch):
    c, *_ = env
    await c.post("/api/v1/apps/apks", files={"file": ("a.apk", make_apk_bytes())})

    def handler(args, serial):
        if serial == "192.168.1.9:5555":
            raise AdbError("adb tamat masa")
        return AdbResult(0, "Success")

    fake_run(monkeypatch, handler)
    r = await c.post("/api/v1/apps/install-many", json={"apk": "a.apk", "device_ids": ["d1", "off", "wifi", "ghost", "d1"]})
    j = r.json()
    res = {x["device_id"]: x for x in j["results"]}
    assert j["total"] == 4 and j["succeeded"] == 1                       # duplicates collapsed
    assert res["d1"]["ok"] and not res["off"]["ok"] and "offline" in res["off"]["message"].lower()
    assert "tamat masa" in res["wifi"]["message"] and "tidak dijumpai" in res["ghost"]["message"]
    assert (await c.post("/api/v1/apps/install-many", json={"apk": "a.apk", "device_ids": []})).status_code == 400


@pytest.mark.asyncio
async def test_package_actions_validate_names(env, monkeypatch):
    c, *_ = env
    seen = []

    def handler(args, serial):
        seen.append(args)
        return AdbResult(0, "package:com.b\npackage:com.a.x\n" if "list" in args else "Success")

    fake_run(monkeypatch, handler)
    assert (await c.get("/api/v1/apps/d1/packages")).json() == {"packages": ["com.a.x", "com.b"], "count": 2}
    assert (await c.post("/api/v1/apps/d1/uninstall", json={"package": "com.a.x"})).json()["ok"]
    n = len(seen)
    assert (await c.post("/api/v1/apps/d1/uninstall", json={"package": "x; reboot"})).status_code == 400
    assert (await c.post("/api/v1/apps/d1/clear-data", json={"package": "$(id)"})).status_code == 400
    assert len(seen) == n


# ── files ─────────────────────────────────────────────────────────────────────

LS = "drwxrwx--x 2 u0_a1 media_rw 4096 2024-05-04 10:11 DCIM\n-rw-rw---- 1 u0_a1 media_rw 12 2024-06-01 09:30 a.txt\n"


@pytest.mark.asyncio
async def test_list_files_and_errors(env, monkeypatch):
    c, *_ = env
    fake_run(monkeypatch, lambda a, s: AdbResult(0, LS))
    j = (await c.get("/api/v1/files/d1/list", params={"path": "/sdcard"})).json()
    assert j["path"] == "/sdcard" and j["parent"] == "/" and [e["name"] for e in j["entries"]] == ["DCIM", "a.txt"]
    assert (await c.get("/api/v1/files/d1/list", params={"path": "relative"})).status_code == 400
    assert (await c.get("/api/v1/files/d1/list", params={"path": "/sdcard/../data"})).status_code == 400
    fake_run(monkeypatch, lambda a, s: AdbResult(1, "", "ls: /nope/: No such file or directory"))
    assert (await c.get("/api/v1/files/d1/list", params={"path": "/nope"})).status_code == 400


@pytest.mark.asyncio
async def test_file_mutations_and_protection(env, monkeypatch):
    c, *_ = env
    cmds = []

    def handler(args, serial):
        cmds.append(args)
        return AdbResult(0, "")

    fake_run(monkeypatch, handler)
    assert (await c.post("/api/v1/files/d1/mkdir", json={"path": "/sdcard/New Folder"})).json()["ok"]
    assert (await c.post("/api/v1/files/d1/delete", json={"path": "/sdcard"})).status_code == 400
    assert (await c.post("/api/v1/files/d1/delete", json={"path": "/"})).status_code == 400
    assert (await c.post("/api/v1/files/d1/rename", json={"path": "/sdcard/a", "new_name": "../b"})).status_code == 400
    r = await c.post("/api/v1/files/d1/rename", json={"path": "/sdcard/a", "new_name": "b"})
    assert r.json()["path"] == "/sdcard/b"
    assert [x[1] for x in cmds] == ["mkdir -p '/sdcard/New Folder'", "mv '/sdcard/a' '/sdcard/b'"]


@pytest.mark.asyncio
async def test_upload_pushes_each_file_and_cleans_temp(env, monkeypatch):
    c, *_ = env
    pushed = []

    async def push(serial, local, remote_dir, name=None):
        pushed.append((serial, local.read_bytes(), remote_dir, name))
        return f"{remote_dir}/{name}"

    monkeypatch.setattr(device_ops, "push_file", push)
    r = await c.post("/api/v1/files/d1/upload", params={"dir": "/sdcard/Download"},
                     files=[("files", ("one.txt", b"111")), ("files", ("../../two.bin", b"22"))])
    j = r.json()
    assert j["succeeded"] == 2
    assert pushed == [("SER1", b"111", "/sdcard/Download", "one.txt"), ("SER1", b"22", "/sdcard/Download", "two.bin")]
    assert not [p for p in rp.data_dir().iterdir() if p.name.startswith("mh-up-")]


@pytest.mark.asyncio
async def test_upload_reports_per_file_failure(env, monkeypatch):
    c, *_ = env

    async def push(serial, local, remote_dir, name=None):
        if name == "bad.txt":
            raise AdbError("No space left")
        return f"{remote_dir}/{name}"

    monkeypatch.setattr(device_ops, "push_file", push)
    r = await c.post("/api/v1/files/d1/upload", files=[("files", ("good.txt", b"1")), ("files", ("bad.txt", b"2"))])
    res = {x["name"]: x for x in r.json()["results"]}
    assert res["good.txt"]["ok"] and not res["bad.txt"]["ok"]


@pytest.mark.asyncio
async def test_download_streams_and_cleans(env, monkeypatch):
    c, *_ = env

    async def pull(serial, remote, local):
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b"hello")
        return local

    monkeypatch.setattr(device_ops, "pull_file", pull)
    r = await c.get("/api/v1/files/d1/download", params={"path": "/sdcard/Download/a b.txt"})
    assert r.status_code == 200 and r.content == b"hello" and "a%20b.txt" in r.headers["content-disposition"]
    assert not [p for p in rp.data_dir().iterdir() if p.name.startswith("mh-dl-")]
    assert (await c.get("/api/v1/files/d1/download", params={"path": "/"})).status_code == 400
