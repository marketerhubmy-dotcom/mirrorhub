from fastapi import WebSocket, WebSocketDisconnect

from app.websocket.manager import manager


async def execution_view_endpoint(device_id: str, ws: WebSocket) -> None:
    """Browser execution monitor → receives live execution state JSON."""
    await manager.connect_execution_viewer(device_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect_execution_viewer(device_id, ws)
