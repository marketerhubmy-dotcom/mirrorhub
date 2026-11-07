from fastapi import WebSocket
from collections import defaultdict


class ConnectionManager:
    """Tracks active WebSocket connections per device_id."""

    def __init__(self) -> None:
        # device_id → list of browser viewer sockets
        self._viewers: dict[str, list[WebSocket]] = defaultdict(list)
        # device_id → android agent socket (only one per device)
        self._agents: dict[str, WebSocket] = {}
        # device_id → list of execution monitor sockets
        self._execution_viewers: dict[str, list[WebSocket]] = defaultdict(list)
        # device_id → list of vision debugger sockets
        self._vision_viewers: dict[str, list[WebSocket]] = defaultdict(list)
        # channel_id → workflow/recorder viewers (channel = workflow_id or session_id)
        self._workflow_viewers: dict[str, list[WebSocket]] = defaultdict(list)
        # channel_id → campaign/queue viewers ("queue" or str(campaign_id))
        self._campaign_viewers: dict[str, list[WebSocket]] = defaultdict(list)
        # channel_id → orchestrator fleet viewers ("fleet" or device_id)
        self._orchestrator_viewers: dict[str, list[WebSocket]] = defaultdict(list)
        # global agent event viewers (all agent events broadcast to all)
        self._agent_viewers: list[WebSocket] = []

    async def connect_viewer(self, device_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._viewers[device_id].append(ws)

    async def disconnect_viewer(self, device_id: str, ws: WebSocket) -> None:
        self._viewers[device_id].remove(ws)

    async def connect_agent(self, device_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._agents[device_id] = ws

    def disconnect_agent(self, device_id: str) -> None:
        self._agents.pop(device_id, None)

    async def broadcast_frame(self, device_id: str, data: bytes) -> None:
        """Send a raw screen frame to all browser viewers."""
        dead: list[WebSocket] = []
        for ws in self._viewers.get(device_id, []):
            try:
                await ws.send_bytes(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._viewers[device_id].remove(ws)

    async def send_control(self, device_id: str, payload: dict) -> bool:
        """Forward a control command to the Android agent. Returns False if agent not connected."""
        agent = self._agents.get(device_id)
        if agent is None:
            return False
        try:
            await agent.send_json(payload)
            return True
        except Exception:
            self.disconnect_agent(device_id)
            return False

    def is_agent_connected(self, device_id: str) -> bool:
        return device_id in self._agents

    async def connect_execution_viewer(self, device_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._execution_viewers[device_id].append(ws)

    async def disconnect_execution_viewer(self, device_id: str, ws: WebSocket) -> None:
        viewers = self._execution_viewers.get(device_id, [])
        if ws in viewers:
            viewers.remove(ws)

    async def broadcast_execution(self, device_id: str, data: str) -> None:
        """Send execution state JSON to all monitors watching this device."""
        dead: list[WebSocket] = []
        for ws in self._execution_viewers.get(device_id, []):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            viewers = self._execution_viewers.get(device_id, [])
            if ws in viewers:
                viewers.remove(ws)


    async def connect_vision_viewer(self, device_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._vision_viewers[device_id].append(ws)

    async def disconnect_vision_viewer(self, device_id: str, ws: WebSocket) -> None:
        viewers = self._vision_viewers.get(device_id, [])
        if ws in viewers:
            viewers.remove(ws)

    async def broadcast_vision(self, device_id: str, data: str) -> None:
        """Send ScreenAnalysis JSON to all vision debugger clients watching this device."""
        dead: list[WebSocket] = []
        for ws in self._vision_viewers.get(device_id, []):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            viewers = self._vision_viewers.get(device_id, [])
            if ws in viewers:
                viewers.remove(ws)


    async def connect_workflow_viewer(self, channel_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._workflow_viewers[channel_id].append(ws)

    async def disconnect_workflow_viewer(self, channel_id: str, ws: WebSocket) -> None:
        viewers = self._workflow_viewers.get(channel_id, [])
        if ws in viewers:
            viewers.remove(ws)

    async def broadcast_workflow(self, channel_id: str, data: str) -> None:
        """Send workflow/recorder event to all clients on this channel."""
        dead: list[WebSocket] = []
        for ws in self._workflow_viewers.get(channel_id, []):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            viewers = self._workflow_viewers.get(channel_id, [])
            if ws in viewers:
                viewers.remove(ws)


    async def connect_campaign_viewer(self, channel_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._campaign_viewers[channel_id].append(ws)

    async def disconnect_campaign_viewer(self, channel_id: str, ws: WebSocket) -> None:
        viewers = self._campaign_viewers.get(channel_id, [])
        if ws in viewers:
            viewers.remove(ws)

    async def broadcast_campaign(self, channel_id: str, data: str) -> None:
        """Send campaign/queue JSON to all clients on this channel."""
        dead: list[WebSocket] = []
        for ws in self._campaign_viewers.get(channel_id, []):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            viewers = self._campaign_viewers.get(channel_id, [])
            if ws in viewers:
                viewers.remove(ws)


    async def connect_orchestrator_viewer(self, channel_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._orchestrator_viewers[channel_id].append(ws)

    async def disconnect_orchestrator_viewer(self, channel_id: str, ws: WebSocket) -> None:
        viewers = self._orchestrator_viewers.get(channel_id, [])
        if ws in viewers:
            viewers.remove(ws)

    async def broadcast_orchestrator(self, data: str) -> None:
        """Broadcast an orchestrator event to ALL orchestrator viewers across all channels."""
        for channel_viewers in list(self._orchestrator_viewers.values()):
            dead: list[WebSocket] = []
            for ws in channel_viewers:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in channel_viewers:
                    channel_viewers.remove(ws)


    async def connect_agent_viewer(self, ws: WebSocket) -> None:
        await ws.accept()
        self._agent_viewers.append(ws)

    async def disconnect_agent_viewer(self, ws: WebSocket) -> None:
        if ws in self._agent_viewers:
            self._agent_viewers.remove(ws)

    async def broadcast_agent(self, data: str) -> None:
        """Broadcast an AI agent event to all connected agent viewers."""
        dead: list[WebSocket] = []
        for ws in list(self._agent_viewers):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._agent_viewers:
                self._agent_viewers.remove(ws)


manager = ConnectionManager()
