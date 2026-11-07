import json
from datetime import datetime, timezone
from sqlalchemy import Text, Integer, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    application: Mapped[str] = mapped_column(Text, default="generic")
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    variables_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "application": self.application,
            "current_version": self.current_version,
            "variables": json.loads(self.variables_json or "[]"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    variables_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "version": self.version,
            "steps": json.loads(self.steps_json or "[]"),
            "variables": json.loads(self.variables_json or "[]"),
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(Integer)
    order: Mapped[int] = mapped_column(Integer, default=0)
    step_type: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text, default="")
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    conditions_json: Mapped[str] = mapped_column(Text, default="{}")
    retry_max: Mapped[int] = mapped_column(Integer, default=2)
    timeout: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    screen_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "order": self.order,
            "step_type": self.step_type,
            "label": self.label,
            "parameters": json.loads(self.parameters_json or "{}"),
            "conditions": json.loads(self.conditions_json or "{}"),
            "retry_max": self.retry_max,
            "timeout": self.timeout,
            "enabled": self.enabled,
            "screen_name": self.screen_name,
            "screenshot_path": self.screenshot_path,
        }


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(Integer)
    workflow_version: Mapped[int] = mapped_column(Integer, default=0)
    device_id: Mapped[str] = mapped_column(Text)
    adb_address: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="RUNNING")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_step_index: Mapped[int] = mapped_column(Integer, default=-1)
    variables_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs_json: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "workflow_version": self.workflow_version,
            "device_id": self.device_id,
            "adb_address": self.adb_address,
            "status": self.status,
            "progress": self.progress,
            "current_step_index": self.current_step_index,
            "variables": json.loads(self.variables_json or "{}"),
            "error": self.error,
            "logs": json.loads(self.logs_json or "[]"),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
