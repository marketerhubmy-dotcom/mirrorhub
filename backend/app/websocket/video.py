from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.registry import get_device
from app.services import h264_stream


async def video_endpoint(device_id: str, ws: WebSocket, db: AsyncSession) -> None:
    """Stream H264 from ADB screenrecord to browser via WebSocket."""
    await ws.accept()

    device = await get_device(db, device_id)
    if not device or not device.adb_address:
        await ws.close()
        return

    async def send_chunk(data: bytes) -> None:
        await ws.send_bytes(data)

    await h264_stream.add_viewer(device_id, device.adb_address, send_chunk)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        h264_stream.remove_viewer(device_id, send_chunk)
