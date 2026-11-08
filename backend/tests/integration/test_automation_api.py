"""Automation core HTTP API + legacy runner hardening."""
import asyncio

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.automation_core import router
from app.automation import core
from app.models.database import get_db
from app.models.device import Device
from tests.unit.test_automation_core import FakeDriver


@pytest_asyncio.fixture()
async def env(db_engine, monkeypatch):
    sf = async_sessionmaker(db_engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def _db():
        async with sf() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    eng = core.AutomationEngine(driver_factory=FakeDriver)
    monkeypatch.setattr(core, "_engine", eng)
    FakeDriver.calls = {}
    FakeDriver.fail_first = {}
    FakeDriver.hang = set()
    async with sf() as s:
        s.add(Device(device_id="on1", device_name="One", adb_address="S1", is_online=True))
        s.add(Device(device_id="on2", device_name="Two", adb_address="S2", is_online=True))
        s.add(Device(device_id="off", device_name="Off", adb_address="S3", is_online=False))
        await s.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as c:
        yield c, eng


STEPS = [{"type": "tap", "x": 0.5, "y": 0.5}, {"type": "text", "value": "hello"}]


@pytest.mark.asyncio
async def test_step_types_and_validate(env):
    c, _ = env
    types = {t["type"] for t in (await c.get("/api/v1/auto/step-types")).json()}
    assert {"tap", "tap_text", "wait_text", "push_file"} <= types
    r = await c.post("/api/v1/auto/validate", json={"steps": STEPS})
    assert r.status_code == 200 and r.json()["steps"][0]["label"] == "Ketik"
    r = await c.post("/api/v1/auto/validate", json={"steps": [{"type": "tap", "x": 3, "y": 0}]})
    assert r.status_code == 400 and "Langkah 1" in r.json()["detail"]


@pytest.mark.asyncio
async def test_run_lifecycle_over_http(env):
    c, eng = env
    r = await c.post("/api/v1/auto/runs", json={"name": "demo", "device_ids": ["on1", "on2"], "steps": STEPS})
    assert r.status_code == 200
    rid = r.json()["id"]
    await asyncio.gather(*eng.get(rid).tasks)
    j = (await c.get(f"/api/v1/auto/runs/{rid}")).json()
    assert j["state"] == "succeeded" and len(j["devices"]) == 2 and all(d["steps_done"] == 2 for d in j["devices"])
    assert j["devices"][0]["logs"]
    assert [x["id"] for x in (await c.get("/api/v1/auto/runs")).json()][0] == rid
    assert FakeDriver.calls["S1"] == [("tap", 0.5, 0.5), ("text", "hello")]


@pytest.mark.asyncio
async def test_start_rejects_offline_unknown_and_bad_steps(env):
    c, _ = env
    r = await c.post("/api/v1/auto/runs", json={"device_ids": ["on1", "off"], "steps": STEPS})
    assert r.status_code == 409 and "Off: offline" in r.json()["detail"]
    r = await c.post("/api/v1/auto/runs", json={"device_ids": ["ghost"], "steps": STEPS})
    assert r.status_code == 409
    r = await c.post("/api/v1/auto/runs", json={"device_ids": ["on1"], "steps": [{"type": "rm -rf"}]})
    assert r.status_code == 400
    assert (await c.post("/api/v1/auto/runs", json={"device_ids": [], "steps": STEPS})).status_code == 422


@pytest.mark.asyncio
async def test_busy_device_conflict_and_cancel(env):
    c, eng = env
    long = [{"type": "wait", "seconds": 60}]
    rid = (await c.post("/api/v1/auto/runs", json={"device_ids": ["on1"], "steps": long})).json()["id"]
    r = await c.post("/api/v1/auto/runs", json={"device_ids": ["on1"], "steps": STEPS})
    assert r.status_code == 409 and "sedang menjalankan" in r.json()["detail"]
    assert (await c.post(f"/api/v1/auto/runs/{rid}/cancel")).json() == {"ok": True}
    await asyncio.gather(*eng.get(rid).tasks)
    assert (await c.get(f"/api/v1/auto/runs/{rid}")).json()["state"] == "cancelled"
    assert (await c.post("/api/v1/auto/runs/none/cancel")).status_code == 404
    assert (await c.get("/api/v1/auto/runs/none")).status_code == 404


@pytest.mark.asyncio
async def test_legacy_runner_text_goes_through_validated_quoting(monkeypatch):
    """The old runner passed unquoted text to the device shell; it must now use adb_control.input_text."""
    from app.services import adb_control, automation_runner

    sent = []
    monkeypatch.setattr(adb_control, "_send", lambda addr, cmd: sent.append(cmd))
    r = automation_runner.AutomationRunner("d", "SER1")
    await r._type_text("hi; reboot | $(id)\nsecond 'quoted'")
    texts = [c for c in sent if c.startswith("input text")]
    assert texts[0] == "input text 'hi;%sreboot%s|%s$(id)'"                  # metacharacters are inert inside single quotes
    assert texts[1] == "input text 'second%s'\\''quoted'\\'''"
    assert sent.count("input keyevent KEYCODE_ENTER") == 2
