"""
WebSocket endpoint for campaign / queue live updates.

Channel IDs:
    "queue"           — global queue state (all clients monitoring the queue)
    str(campaign_id)  — per-campaign progress updates
"""
from fastapi import WebSocket

from app.websocket.manager import manager


async def campaign_view_endpoint(channel_id: str, ws: WebSocket) -> None:
    await manager.connect_campaign_viewer(channel_id, ws)
    try:
        while True:
            await ws.receive_text()  # keep alive; client sends nothing meaningful
    except Exception:
        pass
    finally:
        await manager.disconnect_campaign_viewer(channel_id, ws)
