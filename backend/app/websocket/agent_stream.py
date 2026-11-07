"""WebSocket endpoint for real-time AI agent events."""
from fastapi import WebSocket

from .manager import manager


async def agent_view_endpoint(ws: WebSocket) -> None:
    await manager.connect_agent_viewer(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        await manager.disconnect_agent_viewer(ws)
