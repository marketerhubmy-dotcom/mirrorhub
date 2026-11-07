from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.websocket.manager import manager
from app.devices.registry import get_device
from app.services import device_stream


async def stream_endpoint(device_id: str, ws: WebSocket) -> None:
    """Android agent → pushes raw frames. Kept for future agent support."""
    await manager.connect_agent(device_id, ws)
    try:
        while True:
            frame = await ws.receive_bytes()
            await manager.broadcast_frame(device_id, frame)
    except WebSocketDisconnect:
        manager.disconnect_agent(device_id)


async def view_endpoint(device_id: str, ws: WebSocket, db: AsyncSession) -> None:
    """Browser viewer — receives frames. Auto-starts ADB screencap if device has adb_address."""
    await manager.connect_viewer(device_id, ws)

    # Start screencap stream for this device if not already running
    device = await get_device(db, device_id)
    if device and device.adb_address:
        device_stream.start(device_id, device.adb_address, manager.broadcast_frame)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_viewer(device_id, ws)
        # Stop screencap if no more viewers watching this device
        if not manager._viewers.get(device_id):
            device_stream.stop(device_id)
