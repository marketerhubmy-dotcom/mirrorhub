"""/ws/devices – pushes device lifecycle events (hot-plug, unauthorized, reconnect, adb outage) to the UI."""
import asyncio
import logging

from fastapi import WebSocket, WebSocketDisconnect

from app.devices.lifecycle import get_monitor

logger = logging.getLogger(__name__)


async def devices_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    mon = get_monitor()
    q = mon.subscribe()
    try:
        await ws.send_json({"type": "snapshot", **mon.snapshot()})

        async def drain_client() -> None:
            while True:
                await ws.receive_text()   # detect disconnect; client sends nothing meaningful

        reader = asyncio.create_task(drain_client())
        try:
            while True:
                getter = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({getter, reader}, return_when=asyncio.FIRST_COMPLETED)
                if reader in done:
                    getter.cancel()
                    break
                await ws.send_json(getter.result())
        finally:
            reader.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        mon.unsubscribe(q)
