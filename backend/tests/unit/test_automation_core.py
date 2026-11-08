"""Automation engine: validation, ordering, retries, timeouts, cancel, parallel devices, exclusivity."""
import asyncio

import pytest

from app.automation import core
from app.automation.core import AutomationEngine, AutomationError, StepValidationError, find_in_hierarchy, validate_steps


class FakeDriver:
    """Records calls; behaviour scripted per serial through class-level knobs."""
    calls: dict[str, list] = {}
    fail_first: dict[tuple[str, str], int] = {}
    hang: set[tuple[str, str]] = set()
    screen_text: dict[str, tuple[int, int] | None] = {}

    def __init__(self, serial):
        self.serial = serial
        FakeDriver.calls.setdefault(serial, [])

    async def _rec(self, name, *a):
        FakeDriver.calls[self.serial].append((name, *a))
        if (self.serial, name) in FakeDriver.hang:
            await asyncio.sleep(60)
        left = FakeDriver.fail_first.get((self.serial, name), 0)
        if left > 0:
            FakeDriver.fail_first[(self.serial, name)] = left - 1
            raise AutomationError("boom")

    async def tap(self, x, y): await self._rec("tap", x, y)
    async def long_press(self, x, y): await self._rec("long_press", x, y)
    async def swipe(self, x1, y1, x2, y2, ms): await self._rec("swipe", x1, y1, x2, y2, ms)
    async def text(self, v): await self._rec("text", v)
    async def key(self, c): await self._rec("key", c)
    async def nav(self, a): await self._rec("nav", a)
    async def open_app(self, p): await self._rec("open_app", p)
    async def close_app(self, p): await self._rec("close_app", p)
    async def tap_px(self, x, y): await self._rec("tap_px", x, y)
    async def screenshot(self, n): await self._rec("screenshot", n); return "x.png"
    async def push(self, l, r): await self._rec("push", l, r)

    async def find_text(self, text, contains):
        await self._rec("find_text", text)
        return FakeDriver.screen_text.get(self.serial)


@pytest.fixture(autouse=True)
def reset():
    FakeDriver.calls = {}
    FakeDriver.fail_first = {}
    FakeDriver.hang = set()
    FakeDriver.screen_text = {}


@pytest.fixture()
def engine():
    return AutomationEngine(driver_factory=FakeDriver)


async def finish(run, timeout=5):
    await asyncio.wait_for(asyncio.gather(*run.tasks), timeout)


def S(*steps):
    return validate_steps(list(steps))


# ── validation ────────────────────────────────────────────────────────────────

def test_valid_steps_normalised_with_defaults():
    s = S({"type": "tap", "x": 0.5, "y": 1})[0]
    assert s["retries"] == 0 and s["timeout"] == 60 and s["label"] == "Ketik" and s["continue_on_error"] is False


@pytest.mark.parametrize("bad,frag", [
    ([], "kosong"),
    ("nope", "kosong"),
    ([{"type": "teleport"}], "tidak dikenali"),
    ([{"type": "tap", "x": 0.5}], "'y' diperlukan"),
    ([{"type": "tap", "x": 1.5, "y": 0}], "antara 0 dan 1"),
    ([{"type": "tap", "x": True, "y": 0}], "antara 0 dan 1"),
    ([{"type": "wait", "seconds": 9999}], "seconds"),
    ([{"type": "wait", "seconds": -1}], "seconds"),
    ([{"type": "open_app", "package": "x; reboot"}], "pakej"),
    ([{"type": "text", "value": "a\nb"}], "text"),
    ([{"type": "key", "code": "KEYCODE_HOME; id"}], "key"),
    ([{"type": "nav", "action": "poweroff"}], "nav"),
    ([{"type": "tap", "x": 0, "y": 0, "retries": 99}], "retries"),
    ([{"type": "tap", "x": 0, "y": 0, "timeout": 0}], "timeout"),
    ([{"type": "swipe", "x1": 0, "y1": 0, "x2": 1, "y2": 1, "ms": 1}], "ms"),
    ([{"type": "tap_text", "text": " "}], "text"),
    ([{"type": "tap_text", "text": "OK", "fallback": [2, 2]}], "antara 0 dan 1"),
    ([{"type": "wait_text", "text": "OK", "fallback": [0, 0]}], "fallback"),
    ([{"type": "push_file", "local": "C:/definitely/not/here.bin", "remote": "/sdcard/x"}], "fail tempatan"),
    ([{"type": "tap", "x": 0, "y": 0}] * 201, "Terlalu banyak"),
])
def test_invalid_steps_rejected_with_position(bad, frag):
    with pytest.raises(StepValidationError) as e:
        validate_steps(bad)
    assert frag in str(e.value)


def test_error_message_names_the_step_number():
    with pytest.raises(StepValidationError, match="Langkah 3"):
        validate_steps([{"type": "wait", "seconds": 0}, {"type": "wait", "seconds": 0}, {"type": "tap", "x": 9, "y": 0}])


def test_push_file_remote_path_guarded(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"1")
    with pytest.raises(StepValidationError):
        validate_steps([{"type": "push_file", "local": str(f), "remote": "/sdcard/../data/x"}])
    assert validate_steps([{"type": "push_file", "local": str(f), "remote": "/sdcard/Download/a.bin"}])


def test_find_in_hierarchy():
    xml = ('UI hierchary dumped to: /dev/tty\n<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
           '<node text="" content-desc="Menu" bounds="[0,0][100,100]"/>'
           '<node text="New chat" content-desc="" bounds="[200,300][400,500]"/>'
           '<node text="Send message now" bounds="[10,10][20,20]"/></hierarchy>UI hierchary dumped to: /dev/tty')
    assert find_in_hierarchy(xml, "new chat") == (300, 400)
    assert find_in_hierarchy(xml, "menu") == (50, 50)                       # content-desc also matches
    assert find_in_hierarchy(xml, "send") is None                           # exact by default
    assert find_in_hierarchy(xml, "send", contains=True) == (15, 15)
    assert find_in_hierarchy("garbage", "x") is None
    assert find_in_hierarchy('<hierarchy><node text="a" bounds="[5,5][5,5]"/></hierarchy>', "a") is None   # empty box


# ── engine ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_steps_run_in_order_and_succeed(engine):
    steps = S({"type": "open_app", "package": "com.a.b"}, {"type": "tap", "x": 0.1, "y": 0.2},
              {"type": "text", "value": "hi"}, {"type": "nav", "action": "home"})
    run = engine.start("t", steps, [("d1", "SER1", "Phone 1")])
    await finish(run)
    assert [c[0] for c in FakeDriver.calls["SER1"]] == ["open_app", "tap", "text", "nav"]
    dr = run.devices["d1"]
    assert (dr.state, dr.steps_done, run.state) == ("succeeded", 4, "succeeded")
    assert "d1" not in engine._busy


@pytest.mark.asyncio
async def test_devices_run_in_parallel(engine):
    steps = S({"type": "wait", "seconds": 0.3})
    t0 = asyncio.get_event_loop().time()
    run = engine.start("p", steps, [(f"d{i}", f"S{i}", f"P{i}") for i in range(5)])
    await finish(run)
    assert asyncio.get_event_loop().time() - t0 < 0.9      # not 5 x 0.3
    assert all(d.state == "succeeded" for d in run.devices.values())


@pytest.mark.asyncio
async def test_one_device_failure_does_not_stop_the_others(engine):
    FakeDriver.fail_first[("BAD", "tap")] = 99
    run = engine.start("f", S({"type": "tap", "x": 0, "y": 0}, {"type": "key", "code": "KEYCODE_HOME"}),
                       [("g", "GOOD", "G"), ("b", "BAD", "B")])
    await finish(run)
    assert run.devices["g"].state == "succeeded" and run.devices["b"].state == "failed"
    assert "Langkah 1" in run.devices["b"].error and run.state == "failed"
    assert [c[0] for c in FakeDriver.calls["BAD"]] == ["tap"]                 # stopped after the failing step
    assert not engine._busy


@pytest.mark.asyncio
async def test_retry_then_succeed(engine):
    FakeDriver.fail_first[("S", "tap")] = 2
    run = engine.start("r", S({"type": "tap", "x": 0, "y": 0, "retries": 2, "retry_delay": 0}), [("d", "S", "P")])
    await finish(run)
    assert run.devices["d"].state == "succeeded"
    assert len([c for c in FakeDriver.calls["S"] if c[0] == "tap"]) == 3
    assert sum(1 for l in run.devices["d"].logs if l["level"] == "warn") == 2


@pytest.mark.asyncio
async def test_retries_exhausted_fails(engine):
    FakeDriver.fail_first[("S", "tap")] = 99
    run = engine.start("r", S({"type": "tap", "x": 0, "y": 0, "retries": 1, "retry_delay": 0}), [("d", "S", "P")])
    await finish(run)
    assert run.devices["d"].state == "failed" and len(FakeDriver.calls["S"]) == 2


@pytest.mark.asyncio
async def test_continue_on_error(engine):
    FakeDriver.fail_first[("S", "tap")] = 99
    run = engine.start("c", S({"type": "tap", "x": 0, "y": 0, "continue_on_error": True}, {"type": "nav", "action": "back"}),
                       [("d", "S", "P")])
    await finish(run)
    assert run.devices["d"].state == "succeeded"
    assert [c[0] for c in FakeDriver.calls["S"]] == ["tap", "nav"]


@pytest.mark.asyncio
async def test_step_timeout(engine):
    FakeDriver.hang.add(("S", "tap"))
    run = engine.start("t", S({"type": "tap", "x": 0, "y": 0, "timeout": 1}), [("d", "S", "P")])
    await finish(run, 6)
    assert run.devices["d"].state == "failed" and "tamat masa" in run.devices["d"].error


@pytest.mark.asyncio
async def test_cancel_interrupts_a_long_wait(engine):
    run = engine.start("w", S({"type": "wait", "seconds": 120}, {"type": "tap", "x": 0, "y": 0}), [("d", "S", "P")])
    await asyncio.sleep(0.1)
    assert engine.cancel(run.id) is True
    await finish(run, 3)
    assert run.devices["d"].state == "cancelled" and run.state == "cancelled"
    assert FakeDriver.calls["S"] == []                           # the tap never ran
    assert not engine._busy


@pytest.mark.asyncio
async def test_cancel_interrupts_a_hung_step(engine):
    FakeDriver.hang.add(("S", "tap"))
    run = engine.start("h", S({"type": "tap", "x": 0, "y": 0, "timeout": 300}), [("d", "S", "P")])
    await asyncio.sleep(0.1)
    engine.cancel(run.id)
    await finish(run, 3)
    assert run.devices["d"].state == "cancelled"


@pytest.mark.asyncio
async def test_cancel_unknown_or_finished_run(engine):
    assert engine.cancel("nope") is False
    run = engine.start("x", S({"type": "wait", "seconds": 0}), [("d", "S", "P")])
    await finish(run)
    assert engine.cancel(run.id) is False


@pytest.mark.asyncio
async def test_device_exclusivity_and_release(engine):
    run = engine.start("a", S({"type": "wait", "seconds": 5}), [("d", "S", "P")])
    with pytest.raises(StepValidationError, match="sedang menjalankan"):
        engine.start("b", S({"type": "wait", "seconds": 0}), [("d", "S", "P"), ("e", "T", "Q")])
    assert "e" not in engine._busy                                # all-or-nothing
    engine.cancel(run.id)
    await finish(run, 3)
    again = engine.start("c", S({"type": "wait", "seconds": 0}), [("d", "S", "P")])
    await finish(again)
    assert again.state == "succeeded"


@pytest.mark.asyncio
async def test_tap_text_found_fallback_and_missing(engine):
    FakeDriver.screen_text["A"] = (111, 222)
    s = S({"type": "tap_text", "text": "OK"})
    r = engine.start("t", s, [("a", "A", "A")])
    await finish(r)
    assert ("tap_px", 111, 222) in FakeDriver.calls["A"]

    s = S({"type": "tap_text", "text": "OK", "fallback": [0.9, 0.9]})
    r = engine.start("t", s, [("b", "B", "B")])
    await finish(r)
    assert ("tap", 0.9, 0.9) in FakeDriver.calls["B"]

    r = engine.start("t", S({"type": "tap_text", "text": "OK"}), [("c", "C", "C")])
    await finish(r)
    assert r.devices["c"].state == "failed" and "tidak dijumpai" in r.devices["c"].error


@pytest.mark.asyncio
async def test_wait_text_appears_later_and_times_out(engine):
    FakeDriver.screen_text["A"] = None

    async def appear():
        await asyncio.sleep(0.4)
        FakeDriver.screen_text["A"] = (1, 1)

    asyncio.create_task(appear())
    r = engine.start("w", S({"type": "wait_text", "text": "Done", "timeout": 5}), [("a", "A", "A")])
    await finish(r, 6)
    assert r.devices["a"].state == "succeeded"

    FakeDriver.screen_text["B"] = None
    r = engine.start("w", S({"type": "wait_text", "text": "Never", "timeout": 2}), [("b", "B", "B")])
    await finish(r, 6)
    assert r.devices["b"].state == "failed"


@pytest.mark.asyncio
async def test_run_history_is_pruned(engine, monkeypatch):
    monkeypatch.setattr(core, "MAX_RUNS_KEPT", 3)
    for i in range(6):
        r = engine.start(f"r{i}", S({"type": "wait", "seconds": 0}), [("d", "S", "P")])
        await finish(r)
    assert len([x for x in engine.runs.values() if x.state != "running"]) <= 4


@pytest.mark.asyncio
async def test_shutdown_cancels_running_work(engine):
    r = engine.start("s", S({"type": "wait", "seconds": 300}), [("d", "S", "P")])
    await asyncio.sleep(0.05)
    await engine.shutdown()
    assert r.devices["d"].state == "cancelled"


@pytest.mark.asyncio
async def test_no_devices_rejected(engine):
    with pytest.raises(StepValidationError):
        engine.start("x", S({"type": "wait", "seconds": 0}), [])
