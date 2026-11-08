"""
Regression: the video endpoint must never write to the socket from two tasks at once.

Real-hardware bug (2026-11-08): websockets' legacy protocol asserts a single writer while the transport is
flow-control-paused; concurrent send_bytes()/send_json() raised AssertionError and dropped the connection
on every large keyframe. FakeWS below enforces the same rule.
"""
import asyncio
import types

import pytest

from app.services import scrcpy_stream as ss
from app.websocket import video as video_mod


class FakeWS:
    def __init__(self):
        self.query_params = {"profile": "normal"}
        self.busy = False
        self.violations = 0
        self.sent_bytes = 0
        self.sent_json = 0
        self.closed = asyncio.Event()

    async def accept(self): ...

    async def _write(self):
        if self.busy:                       # a second writer while the first is "draining"
            self.violations += 1
            raise AssertionError("concurrent writers")
        self.busy = True
        for _ in range(3):                  # simulated flow-control wait (yields; Windows timers are too coarse for sleep(0.001))
            await asyncio.sleep(0)
        self.busy = False

    async def send_bytes(self, b):
        await self._write()
        self.sent_bytes += 1

    async def send_json(self, m):
        await self._write()
        self.sent_json += 1

    async def receive_text(self):
        await self.closed.wait()
        from starlette.websockets import WebSocketDisconnect
        raise WebSocketDisconnect()

    async def close(self, code=1000): ...


class FakeSession:
    def __init__(self):
        self.hub = ss.StreamHub()
        self.listeners = set()
        self.state = "streaming"
        self.error = ""

    def status(self):
        return {"event": "state", "state": self.state, "error": self.error}

    def emit(self, st):
        self.state = st
        for l in list(self.listeners):
            l(self.status())


@pytest.mark.asyncio
async def test_status_and_video_are_never_written_concurrently(monkeypatch):
    sess = FakeSession()
    viewer = sess.hub.subscribe()
    ws = FakeWS()

    async def get_device(db, did):
        return types.SimpleNamespace(adb_address="SER1")

    class Mgr:
        def attach(self, *a):
            return sess, viewer

        def detach(self, *a): ...

    monkeypatch.setattr(video_mod, "get_device", get_device)
    monkeypatch.setattr(video_mod, "stream_manager", Mgr())

    task = asyncio.create_task(video_mod.video_endpoint("d", ws, None))
    # hammer both producers at the same time, like a keyframe burst + state change
    for i in range(300):
        viewer.queue.put_nowait(b"\x00\x00\x00\x01\x65" + bytes(100))
        if i % 3 == 0:
            sess.emit("reconnecting" if i % 2 else "streaming")
        for _ in range(8):               # the hub queue is bounded: let the writers drain between items
            await asyncio.sleep(0)
    await asyncio.sleep(0.6)
    ws.closed.set()
    await asyncio.wait_for(task, 3)

    assert ws.violations == 0
    assert ws.sent_bytes == 300 and ws.sent_json >= 100
