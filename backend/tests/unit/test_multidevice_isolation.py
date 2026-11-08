"""
Multi-device stability guarantees (software level – real hardware evidence lives in docs/HARDWARE_VALIDATION.md):
* a failing stream never affects another device's stream;
* sessions and server processes are released after the last viewer leaves;
* two sockets / two devices never cross input.
"""
import asyncio

import pytest

from app.services import scrcpy_stream as ss
from tests.unit.test_perf import make_sps

PPS = b"\x00\x00\x00\x01\x68\xce\x3c\x80"
IDR = b"\x00\x00\x00\x01\x65" + bytes(200)
P = b"\x00\x00\x00\x01\x41\x9a" + bytes(60)


class FakeReaderSession(ss.StreamSession):
    """Real StreamSession logic (retry, hub, state machine) with a synthetic scrcpy socket."""
    launches: dict[str, int] = {}
    cleaned: list[str] = []

    async def _launch(self):
        FakeReaderSession.launches[self.serial] = FakeReaderSession.launches.get(self.serial, 0) + 1
        if self.serial == "BAD":
            raise RuntimeError("device exploded")
        reader = asyncio.StreamReader()
        reader.feed_data(make_sps(432, 960) + PPS + IDR)

        async def feeder():
            try:
                while True:
                    await asyncio.sleep(0.02)
                    reader.feed_data(P)
            except asyncio.CancelledError:
                pass
        self._feeder = asyncio.get_running_loop().create_task(feeder())
        return reader

    async def _cleanup(self):
        FakeReaderSession.cleaned.append(self.serial)
        f = getattr(self, "_feeder", None)
        if f:
            f.cancel()


@pytest.fixture()
def mgr(monkeypatch):
    FakeReaderSession.launches = {}
    FakeReaderSession.cleaned = []
    monkeypatch.setattr(ss, "StreamSession", FakeReaderSession)
    monkeypatch.setattr(FakeReaderSession, "MAX_RETRIES", 1)
    monkeypatch.setattr(ss.StreamManager, "IDLE_GRACE", 0.15)
    # no real backoff sleeps
    orig_sleep = asyncio.sleep

    async def fast(d, *a, **k):
        await orig_sleep(min(d, 0.02))
    monkeypatch.setattr(ss.asyncio, "sleep", fast)
    return ss.StreamManager()


async def until(cond, timeout=3.0):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if cond():
            return True
        await asyncio.sleep(0.01)
    return False


@pytest.mark.asyncio
async def test_one_failing_stream_does_not_disturb_the_other(mgr):
    good, gv = mgr.attach("dev-good", "GOOD", "normal")
    bad, bv = mgr.attach("dev-bad", "BAD", "normal")
    assert await until(lambda: bad.state == "failed")
    frames_at_failure = good.hub.frames
    assert await until(lambda: good.hub.frames > frames_at_failure + 5)          # keeps flowing after the other died
    assert good.state == "streaming" and (good.hub.width, good.hub.height) == (432, 960)
    assert gv.queue.qsize() > 0
    assert bad.reconnects >= 1 and bad.last_error_msg == "device exploded"
    await mgr.stop_all()


@pytest.mark.asyncio
async def test_failed_session_is_replaced_on_next_attach_without_touching_others(mgr):
    good, _ = mgr.attach("dev-good", "GOOD", "normal")
    bad, _ = mgr.attach("dev-bad", "BAD", "normal")
    assert await until(lambda: bad.state == "failed")
    again, _ = mgr.attach("dev-bad", "BAD", "normal")
    assert again is not bad                           # fresh session, fresh retry budget
    assert mgr.get("dev-good", "normal") is good      # the healthy session object is untouched
    await mgr.stop_all()


@pytest.mark.asyncio
async def test_sessions_are_released_after_last_viewer_leaves(mgr):
    sess, v1 = mgr.attach("d", "GOOD", "normal")
    _, v2 = mgr.attach("d", "GOOD", "normal")
    assert len(sess.hub.viewers) == 2
    mgr.detach(sess, v1)
    await asyncio.sleep(0.4)
    assert mgr.get("d", "normal") is sess and sess.state == "streaming"           # one viewer left: stays up
    mgr.detach(sess, v2)
    assert await until(lambda: mgr.get("d", "normal") is None)                    # released after the grace period
    assert sess.state == "stopped" and "GOOD" in FakeReaderSession.cleaned
    assert not mgr._reapers


@pytest.mark.asyncio
async def test_reattach_within_grace_cancels_release(mgr):
    sess, v1 = mgr.attach("d", "GOOD", "normal")
    mgr.detach(sess, v1)
    again, v2 = mgr.attach("d", "GOOD", "normal")                                  # e.g. user switches layout quickly
    await asyncio.sleep(0.4)
    assert again is sess and sess.state == "streaming" and len(sess.hub.viewers) == 1
    await mgr.stop_all()


@pytest.mark.asyncio
async def test_stop_device_stops_every_profile_of_that_device_only(mgr):
    a1, _ = mgr.attach("A", "GOOD", "thumb")
    a2, _ = mgr.attach("A", "GOOD", "focus")
    b, _ = mgr.attach("B", "GOOD2", "normal")
    await mgr.stop_device("A")
    assert a1.state == "stopped" and a2.state == "stopped" and b.state == "streaming"
    await mgr.stop_all()


@pytest.mark.asyncio
async def test_slow_viewer_cannot_block_a_fast_viewer_or_other_devices():
    hub = ss.StreamHub(viewer_queue=3)
    slow, fast = hub.subscribe(), hub.subscribe()
    sps = make_sps(432, 960)
    hub.push(sps + PPS + IDR)
    drained = 0
    for _ in range(50):
        hub.push(P)
        while not fast.queue.empty():
            fast.queue.get_nowait()
            drained += 1
    assert drained >= 40 and hub.dropped > 0 and slow.waiting_key         # slow viewer resyncs at next keyframe, fast one never stalled
    other = ss.StreamHub()
    other.push(sps + PPS + IDR)
    assert other.frames == 1 and other.dropped == 0                        # a different device's hub is independent


def test_control_commands_are_bound_to_their_own_device_only(monkeypatch):
    """Two control sockets, two devices: every tap reaches exactly the serial of ITS device."""
    from app.services import adb_control
    from app.websocket.control import check_binding, dispatch_adb
    sent = []
    monkeypatch.setattr(adb_control, "tap", lambda addr, x, y: sent.append((addr, x, y)))
    for dev_id, serial in (("id-A", "SER-A"), ("id-B", "SER-B"), ("id-A", "SER-A")):
        payload = check_binding(dev_id, {"type": "tap", "x": 0.1, "y": 0.2, "device_id": dev_id})
        dispatch_adb(serial, payload)
    assert [s for s, *_ in sent] == ["SER-A", "SER-B", "SER-A"]
    with pytest.raises(Exception):
        check_binding("id-A", {"type": "tap", "x": 0.1, "y": 0.2, "device_id": "id-B"})     # cross-device claim rejected
