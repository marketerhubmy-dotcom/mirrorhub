import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.websocket.manager import manager
from app.devices.registry import get_device
from app.services import adb_control
from app.services.device_stream import request_capture


async def control_endpoint(device_id: str, ws: WebSocket, db: AsyncSession) -> None:
    await ws.accept()

    device = await get_device(db, device_id)
    adb_address = device.adb_address if device else None

    try:
        while True:
            payload = await ws.receive_json()
            if adb_address:
                await _dispatch_adb(adb_address, payload)
                request_capture(device_id)  # refresh screen immediately
            else:
                delivered = await manager.send_control(device_id, payload)
                if not delivered:
                    await ws.send_json({"error": "device_not_connected"})
    except WebSocketDisconnect:
        pass


async def _dispatch_adb(adb_address: str, payload: dict) -> None:
    t = payload.get("type")
    try:
        if t == "tap":
            await asyncio.to_thread(adb_control.tap, adb_address, payload["x"], payload["y"])
        elif t == "long_press":
            await asyncio.to_thread(adb_control.long_press, adb_address, payload["x"], payload["y"])
        elif t == "swipe":
            await asyncio.to_thread(
                adb_control.swipe, adb_address,
                payload["x1"], payload["y1"], payload["x2"], payload["y2"],
            )
        elif t == "text":
            await asyncio.to_thread(adb_control.input_text, adb_address, payload["value"])
        elif t == "key":
            await asyncio.to_thread(adb_control.keyevent, adb_address, payload["code"])
        elif t == "nav":
            await asyncio.to_thread(adb_control.nav, adb_address, payload["action"])
    except Exception:
        pass
