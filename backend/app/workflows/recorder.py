"""
Workflow Recorder.

Recording sessions are in-memory.  When the user calls stop(), the session is
persisted to the DB as a new Workflow + its initial steps.

Usage:
    POST /workflows/recorder/start  → { session_id }
    POST /workflows/recorder/{id}/step   → adds a step
    GET  /workflows/recorder/{id}        → session state
    POST /workflows/recorder/{id}/stop   → saves and returns workflow
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

_sessions: dict[str, "RecordingSession"] = {}


@dataclass
class RecordingSession:
    session_id: str
    device_id: str
    adb_address: str
    name: str
    started_at: datetime
    steps: list[dict] = field(default_factory=list)

    def add_step(self, step_type: str, label: str = "", parameters: dict | None = None,
                 conditions: dict | None = None, screen_name: str | None = None,
                 screenshot_path: str | None = None) -> dict:
        step = {
            "order": len(self.steps),
            "step_type": step_type,
            "label": label or step_type,
            "parameters": parameters or {},
            "conditions": conditions or {},
            "retry_max": 2,
            "timeout": 30,
            "enabled": True,
            "screen_name": screen_name,
            "screenshot_path": screenshot_path,
        }
        self.steps.append(step)
        return step

    def remove_step(self, index: int) -> bool:
        if 0 <= index < len(self.steps):
            self.steps.pop(index)
            # Re-number
            for i, s in enumerate(self.steps):
                s["order"] = i
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "name": self.name,
            "started_at": self.started_at.isoformat(),
            "step_count": len(self.steps),
            "steps": self.steps,
        }


def start_session(device_id: str, adb_address: str, name: str = "New Recording") -> RecordingSession:
    sid = str(uuid.uuid4())[:8]
    session = RecordingSession(
        session_id=sid,
        device_id=device_id,
        adb_address=adb_address,
        name=name,
        started_at=datetime.now(timezone.utc),
    )
    _sessions[sid] = session
    return session


def get_session(session_id: str) -> RecordingSession | None:
    return _sessions.get(session_id)


def remove_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def list_sessions() -> list[dict]:
    return [s.to_dict() for s in _sessions.values()]


async def capture_step_context(adb_address: str, device_id: str) -> tuple[str | None, str | None]:
    """
    Take a screenshot + run Vision Engine to get current screen context.
    Returns (screen_name, screenshot_web_path).
    Called when adding a step with capture_screen=True.
    """
    try:
        from app.vision.analyzer import analyze_screen
        analysis = await analyze_screen(adb_address, device_id, use_cache_ms=2000)
        return analysis.screen_name, analysis.screenshot_path
    except Exception:
        return None, None
