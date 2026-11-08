"""
DeviceMonitor state machine, driven by a scripted fake adb (no hardware).

This proves lifecycle LOGIC (hot-plug, unauthorized, USB<->WiFi identity,
auto-reconnect, adb outage).  It does not prove real devices behave this way.
"""
import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.devices.lifecycle import DeviceMonitor, new_device_id, tags_to_list
from app.models.device import Device
from app.services.adb_client import AdbDevice, AdbError, AdbMissing
from app.services.device_info import DeviceInfo


def dev(serial, state="device", transport=None):
    from app.services.adb_client import classify_transport
    return AdbDevice(serial=serial, state=state, transport=transport or classify_transport(serial), model="Pixel_7")


class Script:
    """Mutable fake world the monitor observes."""
    def __init__(self):
        self.devices: list[AdbDevice] = []
        self.fail: Exception | None = None
        self.hw = {}          # adb serial -> hw serial
        self.connects: list[str] = []
        self.connect_ok = False
        self.input = ("ok", "")
        self.mdns = {}        # mdns serial -> current ip:port (None = not advertised)

    async def lister(self):
        if self.fail:
            raise self.fail
        return list(self.devices)

    async def info(self, serial):
        return DeviceInfo(model="Pixel 7", manufacturer="Google", android_version="14", sdk=34,
                          hw_serial=self.hw.get(serial, serial), battery=77, screen_w=1080, screen_h=2400,
                          storage_total_mb=1000, storage_free_mb=400)

    async def resolve(self, serial, hw):
        if serial in self.mdns:
            return self.mdns[serial]
        return serial

    async def probe(self, serial):
        return self.input

    async def connect(self, addr):
        self.connects.append(addr)
        return self.connect_ok, "connected to" if self.connect_ok else "failed"


@pytest.fixture()
def world(db_engine):
    sf = async_sessionmaker(db_engine, expire_on_commit=False)
    s = Script()
    m = DeviceMonitor(session_factory=sf, lister=s.lister, info_fetcher=s.info, connector=s.connect, resolver=s.resolve,
                      poll_interval=0.01, backoff=(0.01, 0.01, 0.01), info_retries=3, info_retry_delay=0,
                      input_prober=s.probe)
    return m, s, sf


async def settle(m):
    """Let spawned DB tasks finish."""
    for _ in range(50):
        await asyncio.sleep(0)
        if not m._bg:
            break
    await asyncio.sleep(0.02)
    while m._bg:
        await asyncio.gather(*list(m._bg), return_exceptions=True)


async def rows(sf):
    async with sf() as db:
        return list((await db.execute(select(Device))).scalars())


@pytest.mark.asyncio
async def test_plug_in_registers_device_with_facts(world):
    m, s, sf = world
    q = m.subscribe()
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    r = await rows(sf)
    assert len(r) == 1
    d = r[0]
    assert (d.is_online, d.state, d.transport, d.adb_address) == (True, "online", "usb", "USB123")
    assert (d.model, d.android_version, d.sdk, d.battery, d.screen_w) == ("Pixel 7", "14", 34, 77, 1080)
    assert d.hw_serial == "USB123"
    kinds = []
    while not q.empty():
        e = q.get_nowait(); kinds.append((e["type"], e.get("action")))
    assert ("device", "appeared") in kinds and ("device", "online") in kinds


@pytest.mark.asyncio
async def test_unplug_marks_offline_and_replug_restores(world):
    m, s, sf = world
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    s.devices = []
    await m.tick(); await settle(m)
    d = (await rows(sf))[0]
    assert (d.is_online, d.state) == (False, "offline")
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    rs = await rows(sf)
    assert len(rs) == 1 and rs[0].is_online and rs[0].state == "online"


@pytest.mark.asyncio
async def test_unauthorized_is_persisted_with_instruction(world):
    m, s, sf = world
    s.devices = [dev("UNAUTH1", "unauthorized")]
    await m.tick(); await settle(m)
    d = (await rows(sf))[0]
    assert d.state == "unauthorized" and not d.is_online and "Allow" in d.last_error
    # user taps Allow
    s.devices = [dev("UNAUTH1", "device")]
    await m.tick(); await settle(m)
    rs = await rows(sf)
    assert len(rs) == 1 and rs[0].state == "online" and rs[0].last_error == ""


@pytest.mark.asyncio
async def test_same_phone_over_usb_and_wifi_is_one_device(world):
    m, s, sf = world
    s.hw = {"USB123": "HWSER", "192.168.1.9:5555": "HWSER"}
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    s.devices = [dev("USB123"), dev("192.168.1.9:5555")]
    await m.tick(); await settle(m)
    rs = await rows(sf)
    assert len(rs) == 1
    assert rs[0].adb_address == "USB123" and rs[0].transport == "usb"      # USB stays preferred
    # USB cable pulled: fall over to WiFi without going offline
    s.devices = [dev("192.168.1.9:5555")]
    await m.tick(); await settle(m)
    d = (await rows(sf))[0]
    assert d.adb_address == "192.168.1.9:5555" and d.transport == "wifi" and d.is_online


@pytest.mark.asyncio
async def test_wifi_drop_triggers_reconnect_attempts_then_gives_up(world):
    m, s, sf = world
    s.devices = [dev("192.168.1.9:5555")]
    await m.tick(); await settle(m)
    s.devices = []
    await m.tick(); await settle(m)
    await asyncio.wait_for(asyncio.gather(*list(m._reconnect.values())), 2)
    assert s.connects == ["192.168.1.9:5555"] * 3
    d = (await rows(sf))[0]
    assert d.state == "offline" and "Pairing Center" in d.last_error


@pytest.mark.asyncio
async def test_reconnect_stops_when_device_returns(world):
    m, s, sf = world
    s.devices = [dev("192.168.1.9:5555")]
    await m.tick(); await settle(m)
    s.connect_ok = True          # set BEFORE the drop so the first attempt deterministically succeeds
    s.devices = []
    await m.tick(); await settle(m)
    await asyncio.wait_for(asyncio.gather(*list(m._reconnect.values())), 2)
    assert len(s.connects) == 1


@pytest.mark.asyncio
async def test_user_disconnect_suppresses_reconnect(world):
    m, s, sf = world
    s.devices = [dev("192.168.1.9:5555")]
    await m.tick(); await settle(m)
    m.suppress_reconnect("192.168.1.9:5555")
    s.devices = []
    await m.tick(); await settle(m)
    await asyncio.sleep(0.1)
    assert s.connects == [] and not m._reconnect


@pytest.mark.asyncio
async def test_usb_never_auto_reconnects(world):
    m, s, sf = world
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    s.devices = []
    await m.tick(); await settle(m)
    await asyncio.sleep(0.1)
    assert s.connects == []


@pytest.mark.asyncio
async def test_adb_outage_is_reported_once_and_recovers(world, monkeypatch):
    m, s, sf = world
    started = []

    async def fake_start():
        started.append(1)

    monkeypatch.setattr("app.devices.lifecycle.adb_client.start_server", fake_start)
    q = m.subscribe()
    s.fail = AdbError("daemon not running")
    await m.tick(); await m.tick()
    assert m.adb_ok is False and m.last_error == "daemon not running" and started
    s.fail = None
    await m.tick()
    assert m.adb_ok is True
    evs = []
    while not q.empty():
        evs.append(q.get_nowait())
    adb_evs = [e for e in evs if e["type"] == "adb"]
    assert [e["ok"] for e in adb_evs] == [False, True]   # one failure event, one recovery


@pytest.mark.asyncio
async def test_missing_adb_is_reported(world):
    m, s, sf = world
    s.fail = AdbMissing("adb.exe tidak dijumpai")
    await m.tick()
    assert not m.adb_ok and "adb.exe" in m.snapshot()["error"]


@pytest.mark.asyncio
async def test_info_failure_still_registers_device(world):
    m, s, sf = world

    async def boom(serial):
        raise AdbError("shell not ready")

    m._info = boom
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    d = (await rows(sf))[0]
    assert d.is_online and "tidak dapat dibaca" in d.last_error


@pytest.mark.asyncio
async def test_background_loop_survives_exceptions(world):
    m, s, sf = world
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return []

    m._list = flaky
    m.start()
    assert await m.wait_first_tick(2)
    await asyncio.sleep(0.1)
    assert calls["n"] >= 2
    await m.stop()


@pytest.mark.asyncio
async def test_legacy_device_matched_by_adb_address_keeps_id(world):
    m, s, sf = world
    legacy_id = new_device_id("USB123", None)
    async with sf() as db:
        db.add(Device(device_id=legacy_id, device_name="My Phone", adb_address="USB123"))
        await db.commit()
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    rs = await rows(sf)
    assert len(rs) == 1 and rs[0].device_id == legacy_id and rs[0].device_name == "My Phone"  # name not overwritten


def test_helpers():
    assert new_device_id("a:1", None) == new_device_id("a:1", None)
    assert new_device_id("a:1", "HW") == new_device_id("b:2", "HW")
    assert tags_to_list('["a","b"]') == ["a", "b"]
    assert tags_to_list("not json") == [] and tags_to_list(None) == [] and tags_to_list('{"a":1}') == []


@pytest.mark.asyncio
async def test_info_retries_then_succeeds(world):
    m, s, sf = world
    calls = {"n": 0}
    real = s.info

    async def flaky(serial):
        calls["n"] += 1
        if calls["n"] < 3:
            raise AdbError("error: closed")
        return await real(serial)

    m._info = flaky
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    d = (await rows(sf))[0]
    assert calls["n"] == 3 and d.model == "Pixel 7" and d.last_error == ""


@pytest.mark.asyncio
async def test_startup_reconcile_marks_stale_online_rows_offline(world):
    m, s, sf = world
    async with sf() as db:
        db.add(Device(device_id="ghost", device_name="ghost", adb_address="1.2.3.4:5555", is_online=True))
        db.add(Device(device_id="live", device_name="live", adb_address="USB123", is_online=True))
        await db.commit()
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    by = {r.device_id: r for r in await rows(sf)}
    assert by["ghost"].is_online is False and by["ghost"].state == "offline"
    assert by["live"].is_online is True


@pytest.mark.asyncio
async def test_blocked_input_is_recorded_on_the_device_row(world):
    m, s, sf = world
    s.input = ("blocked", "Telefon menyekat input")
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    assert (await rows(sf))[0].input_state == "blocked"
    s.input = ("ok", "")
    s.devices = []
    await m.tick(); await settle(m)
    s.devices = [dev("USB123")]
    await m.tick(); await settle(m)
    assert (await rows(sf))[0].input_state == "ok"


MDNS = "adb-HW1-abc._adb-tls-connect._tcp"


@pytest.mark.asyncio
async def test_mdns_named_wifi_device_reconnects_to_its_current_address(world):
    """Real-hardware finding 2026-11-08: mDNS-serial devices were never reconnected (only ip:port ones)."""
    m, s, sf = world
    s.hw = {MDNS: "HW1"}
    s.devices = [dev(MDNS)]
    await m.tick(); await settle(m)
    s.mdns[MDNS] = "192.168.0.238:39927"
    s.connect_ok = True
    s.devices = []
    await m.tick(); await settle(m)
    await asyncio.wait_for(asyncio.gather(*list(m._reconnect.values())), 2)
    assert s.connects == ["192.168.0.238:39927"]           # connected to the resolved address, not the mDNS name


@pytest.mark.asyncio
async def test_unresolvable_mdns_device_gives_up_with_explanation(world):
    m, s, sf = world
    s.hw = {MDNS: "HW1"}
    s.devices = [dev(MDNS)]
    await m.tick(); await settle(m)
    s.mdns[MDNS] = None
    s.devices = []
    await m.tick(); await settle(m)
    await asyncio.wait_for(asyncio.gather(*list(m._reconnect.values())), 2)
    assert s.connects == []
    assert (await rows(sf))[0].state == "offline"


@pytest.mark.asyncio
async def test_reconnect_now_resolves_and_reports(world):
    m, s, sf = world
    s.mdns[MDNS] = None
    ok, msg = await m.reconnect_now(MDNS)
    assert ok is False and "mDNS" in msg
    s.mdns[MDNS] = "10.0.0.5:4444"
    s.connect_ok = True
    assert (await m.reconnect_now(MDNS))[0] is True and s.connects == ["10.0.0.5:4444"]
