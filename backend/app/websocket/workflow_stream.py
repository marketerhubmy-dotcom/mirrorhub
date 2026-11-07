from fastapi import WebSocket
from app.websocket.manager import manager


async def workflow_view_endpoint(channel_id: str, ws: WebSocket) -> None:
    """
    channel_id is either:
      - a workflow_id (for playback progress)
      - a session_id  (for recorder events)
    Both share the same broadcast channel in ConnectionManager.
    """
    await manager.connect_workflow_viewer(channel_id, ws)
    try:
        while True:
            await ws.receive_text()  # keep alive; server pushes all updates
    except Exception:
        pass
    finally:
        await manager.disconnect_workflow_viewer(channel_id, ws)
