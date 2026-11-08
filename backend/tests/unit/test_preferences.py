"""Persistent preferences: defaults, validation, atomic persistence, corrupt-file recovery, effect on reconnect."""
import asyncio
import json

import pytest

from app.core import runtime_paths as rp
import app.models.device  # noqa: F401  (register table before the db_engine fixture creates the schema)
from app.services import preferences as prefs


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("MIRRORHUB_DATA_DIR", str(tmp_path / "d"))


def test_defaults_when_no_file():
    assert prefs.load() == prefs.DEFAULTS
    assert prefs.get("auto_reconnect") is True


def test_update_persists_and_survives_reload():
    out = prefs.update({"wall_layout": 4, "wall_show_offline": True, "record_seconds": 30})
    assert out["wall_layout"] == 4
    again = prefs.load()                      # fresh read = what a restart would see
    assert (again["wall_layout"], again["wall_show_offline"], again["record_seconds"]) == (4, True, 30)
    assert again["auto_reconnect"] is True    # untouched keys keep defaults
    assert not list(rp.data_dir().glob("*.tmp"))


@pytest.mark.parametrize("bad", [
    {"wall_layout": 5}, {"wall_layout": "huge"}, {"wall_show_offline": "yes"}, {"record_seconds": 0},
    {"record_seconds": 999}, {"record_seconds": True}, {"wall_quality": "ultra"}, {"nope": 1}, {}, [],
])
def test_invalid_updates_rejected_and_nothing_written(bad):
    with pytest.raises(ValueError):
        prefs.update(bad)
    assert not (rp.data_dir() / "preferences.json").exists()


def test_partial_invalid_patch_writes_nothing():
    prefs.update({"wall_layout": 2})
    with pytest.raises(ValueError):
        prefs.update({"wall_layout": 9, "record_seconds": -1})
    assert prefs.load()["wall_layout"] == 2


def test_corrupt_file_is_moved_aside_not_deleted():
    p = rp.data_dir() / "preferences.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert prefs.load() == prefs.DEFAULTS
    assert not p.exists()
    assert list(rp.data_dir().glob("preferences.corrupt.*.json"))


def test_bad_single_value_does_not_discard_the_rest():
    (rp.data_dir() / "preferences.json").write_text(json.dumps({"wall_layout": 99, "record_seconds": 45}), encoding="utf-8")
    p = prefs.load()
    assert p["wall_layout"] == "auto" and p["record_seconds"] == 45


@pytest.mark.asyncio
async def test_auto_reconnect_preference_disables_reconnect_loop(db_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.devices.lifecycle import DeviceMonitor
    from app.services.adb_client import AdbDevice
    from app.services.device_info import DeviceInfo

    sf = async_sessionmaker(db_engine, expire_on_commit=False)
    state = {"devs": [AdbDevice("192.168.1.9:5555", "device", "wifi")]}
    connects = []

    async def lister():
        return list(state["devs"])

    async def info(s):
        return DeviceInfo(model="M", hw_serial="HW", sdk=34, screen_w=1)

    async def connect(a):
        connects.append(a)
        return False, "no"

    async def resolve(s, hw):
        return s

    async def probe(s):
        return "ok", ""

    m = DeviceMonitor(session_factory=sf, lister=lister, info_fetcher=info, connector=connect, resolver=resolve,
                      input_prober=probe, backoff=(0.01,), info_retry_delay=0)
    await m.tick()
    await asyncio.sleep(0.1)
    prefs.update({"auto_reconnect": False})
    state["devs"] = []
    await m.tick()
    await asyncio.sleep(0.2)
    assert connects == [] and not m._reconnect
    # and the manual path still works
    ok, _ = await m.reconnect_now("192.168.1.9:5555")
    assert ok is False and connects == ["192.168.1.9:5555"]
