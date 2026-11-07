from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ExecutionStatus(str, Enum):
    WAITING          = "WAITING"
    STARTING         = "STARTING"
    RUNNING          = "RUNNING"
    EXPORTING        = "EXPORTING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"   # STOP_BEFORE_POST: pipeline parked at Publish button
    COMPLETED        = "COMPLETED"
    FAILED           = "FAILED"
    CANCELLED        = "CANCELLED"


class StepResult(str, Enum):
    SUCCESS = "SUCCESS"
    RETRY = "RETRY"
    SKIP = "SKIP"
    ABORT = "ABORT"


@dataclass
class StepState:
    index: int
    label: str
    step_type: str
    status: str = "pending"  # pending / running / success / failed / skipped
    started_at: datetime | None = None
    completed_at: datetime | None = None
    screenshot: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "label": self.label,
            "type": self.step_type,
            "status": self.status,
            "screenshot": self.screenshot,
            "error": self.error,
        }


@dataclass
class ExecutionState:
    job_id: int
    device_id: str
    status: ExecutionStatus = ExecutionStatus.WAITING
    steps: list[StepState] = field(default_factory=list)
    current_index: int = -1
    progress: float = 0.0
    last_screenshot: str | None = None
    current_screen: str = ""
    error: str | None = None
    logs: list[dict] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def current_step(self) -> StepState | None:
        if 0 <= self.current_index < len(self.steps):
            return self.steps[self.current_index]
        return None

    @property
    def next_step(self) -> StepState | None:
        nxt = self.current_index + 1
        if nxt < len(self.steps):
            return self.steps[nxt]
        return None

    @property
    def previous_step(self) -> StepState | None:
        prev = self.current_index - 1
        if prev >= 0:
            return self.steps[prev]
        return None

    def add_log(self, message: str, level: str = "info") -> None:
        self.logs.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        })

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "device_id": self.device_id,
            "status": self.status.value,
            "current_index": self.current_index,
            "progress": self.progress,
            "last_screenshot": self.last_screenshot,
            "current_screen": self.current_screen,
            "error": self.error,
            "current_step": self.current_step.to_dict() if self.current_step else None,
            "next_step": {"label": self.next_step.label} if self.next_step else None,
            "previous_step": self.previous_step.to_dict() if self.previous_step else None,
            "steps": [s.to_dict() for s in self.steps],
            "logs": self.logs[-50:],
        }
