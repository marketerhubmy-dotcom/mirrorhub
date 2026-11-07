from fastapi import WebSocket, WebSocketDisconnect

from app.websocket.manager import manager


async def vision_view_endpoint(device_id: str, ws: WebSocket) -> None:
    """Vision Debugger → receives live ScreenAnalysis updates for a device."""
    await manager.connect_vision_viewer(device_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_vision_viewer(device_id, ws)
