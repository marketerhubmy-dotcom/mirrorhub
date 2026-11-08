import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.registry import get_device
from app.services.adb_control import ControlError, validate_serial
from app.services.scrcpy_stream import PROFILES, stream_manager

logger = logging.getLogger("mirrorhub.stream")


async def video_endpoint(device_id: str, ws: WebSocket, db: AsyncSession) -> None:
    """Embedded H.264 stream for ONE device (ADR-002).

    Binary messages: one Annex-B NAL unit each. Text messages: JSON status events
    ({"event":"state", "state": "...", "error": "..."}).
    Query: ?profile=thumb|normal|focus
    """
    profile = ws.query_params.get("profile", "normal")
    await ws.accept()

    if profile not in PROFILES:
        await ws.send_json({"event": "error", "error": f"unknown profile {profile!r}"})
        await ws.close(code=4400)
        return

    device = await get_device(db, device_id)
    if not device or not device.adb_address:
        await ws.send_json({"event": "error", "error": "device not found or has no ADB address"})
        await ws.close(code=4404)
        return
    try:
        validate_serial(device.adb_address)
    except ControlError:
        await ws.send_json({"event": "error", "error": "invalid device address"})
        await ws.close(code=4400)
        return

    sess, viewer = stream_manager.attach(device_id, device.adb_address, profile)
    status_q: asyncio.Queue = asyncio.Queue(maxsize=16)

    def on_state(msg: dict) -> None:
        try:
            status_q.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    sess.listeners.add(on_state)
    on_state(sess.status())

    # The websockets library allows ONE writer waiting on flow control at a time (`assert waiter is None`
    # in _drain_helper). Video and status writers used to run concurrently, so a large keyframe filling the
    # socket buffer killed the connection with AssertionError -> endless client reconnects. Serialize writes.
    send_lock = asyncio.Lock()

    async def send_video() -> None:
        while True:
            au = await viewer.queue.get()
            async with send_lock:
                await ws.send_bytes(au)

    async def send_status() -> None:
        while True:
            msg = await status_q.get()
            async with send_lock:
                await ws.send_json(msg)

    async def drain_client() -> None:
        while True:  # also detects disconnects; clients may send {"type":"ping"}
            await ws.receive_text()

    tasks = [asyncio.create_task(c()) for c in (send_video, send_status, drain_client)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for d in done:  # why did the socket end? (client left vs server-side failure)
            exc = d.exception() if not d.cancelled() else None
            logger.info("video ws %s/%s ended: %s", device_id[:8], profile, repr(exc) if exc else "task finished", exc_info=exc)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        sess.listeners.discard(on_state)
        stream_manager.detach(sess, viewer)
