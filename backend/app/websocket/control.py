import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.registry import get_device
from app.services import adb_control
from app.services.adb_control import ControlError
from app.services.device_stream import request_capture
from app.websocket.manager import manager

audit = logging.getLogger("mirrorhub.control.audit")

MAX_MESSAGE_TYPES = {"tap", "long_press", "swipe", "text", "key", "nav"}


def check_binding(path_device_id: str, payload: object) -> dict:
    """Return the payload if it is a dict addressed (or unaddressed) to this device.

    A message that names a *different* device_id is rejected so a client bug
    can never steer input to another phone (plan §6: every input carries and
    is checked against its device id).
    """
    if not isinstance(payload, dict):
        raise ControlError("payload must be an object")
    claimed = payload.get("device_id")
    if claimed is not None and claimed != path_device_id:
        raise ControlError("device_id mismatch")
    if payload.get("type") not in MAX_MESSAGE_TYPES:
        raise ControlError("unknown command type")
    return payload


def dispatch_adb(adb_address: str, payload: dict) -> None:
    """Validate and execute one command against ``adb_address`` (blocking)."""
    t = payload["type"]
    try:
        if t == "tap":
            adb_control.tap(adb_address, payload["x"], payload["y"])
        elif t == "long_press":
            adb_control.long_press(adb_address, payload["x"], payload["y"])
        elif t == "swipe":
            adb_control.swipe(adb_address, payload["x1"], payload["y1"], payload["x2"], payload["y2"])
        elif t == "text":
            adb_control.input_text(adb_address, payload["value"])
        elif t == "key":
            adb_control.keyevent(adb_address, payload["code"])
        elif t == "nav":
            adb_control.nav(adb_address, payload["action"])
    except KeyError as exc:
        raise ControlError(f"missing field {exc.args[0]!r}") from exc


async def control_endpoint(device_id: str, ws: WebSocket, db: AsyncSession) -> None:
    await ws.accept()

    device = await get_device(db, device_id)
    adb_address = device.adb_address if device else None

    try:
        while True:
            raw = await ws.receive_json()
            try:
                payload = check_binding(device_id, raw)
                if adb_address:
                    await asyncio.to_thread(dispatch_adb, adb_address, payload)
                    audit.info("device=%s type=%s ok", device_id, payload["type"])
                    request_capture(device_id)  # refresh screen immediately
                else:
                    delivered = await manager.send_control(device_id, payload)
                    if not delivered:
                        await ws.send_json({"error": "device_not_connected"})
            except ControlError as exc:
                audit.warning("device=%s rejected: %s", device_id, exc)
                await ws.send_json({"error": "invalid_command", "detail": str(exc)})
    except WebSocketDisconnect:
        pass
