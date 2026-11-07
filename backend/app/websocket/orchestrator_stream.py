"""WebSocket endpoint for real-time orchestrator events."""
from fastapi import WebSocket

from .manager import manager


async def orchestrator_view_endpoint(channel_id: str, ws: WebSocket) -> None:
    await manager.connect_orchestrator_viewer(channel_id, ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        await manager.disconnect_orchestrator_viewer(channel_id, ws)
