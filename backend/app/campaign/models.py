import json
from datetime import datetime, timezone
from sqlalchemy import Text, Integer, Float, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base
from app.models.types import UTCDateTime

# Priority labels used by CampaignJob.to_dict()
_PRIORITY_LABELS: dict[int, str] = {0: "CRITICAL", 1: "HIGH", 2: "NORMAL", 3: "LOW"}

# Named integer constants — use these instead of bare 0/1/2/3 literals
PRIORITY_CRITICAL = 0
PRIORITY_HIGH = 1
PRIORITY_NORMAL = 2
PRIORITY_LOW = 3


# ── Campaign ──────────────────────────────────────────────────────────────────

class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="DRAFT")
    # defaults applied to each CampaignJob unless overridden
    platform_default: Mapped[str] = mapped_column(Text, default="tiktok")
    device_id_default: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(Text, default="UTC")
    total_jobs: Mapped[int] = mapped_column(Integer, default=0)
    completed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    failed_jobs: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "platform_default": self.platform_default,
            "device_id_default": self.device_id_default,
            "timezone": self.timezone,
            "total_jobs": self.total_jobs,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "progress": round(self.completed_jobs / self.total_jobs * 100, 1) if self.total_jobs else 0.0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── CampaignJob ───────────────────────────────────────────────────────────────

class CampaignJob(Base):
    __tablename__ = "campaign_jobs"
    __table_args__ = (
        Index("ix_campaign_jobs_campaign_id", "campaign_id"),
        Index("ix_campaign_jobs_status", "status"),
        Index("ix_campaign_jobs_device_id", "device_id"),
        Index("ix_campaign_jobs_campaign_status", "campaign_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # FK enforced for new databases; legacy tables created before this lack it (create_all never alters)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"))
    content_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    platform: Mapped[str] = mapped_column(Text, default="tiktok")
    device_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 0=critical 1=high 2=normal 3=low
    scheduled_time: Mapped[datetime | None] = mapped_column(nullable=True)
    schedule_expr: Mapped[str | None] = mapped_column(Text, nullable=True)  # recurring JSON
    depends_on_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_max: Mapped[int] = mapped_column(Integer, default=3)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(Text, default="WAITING")
    job_config_json: Mapped[str] = mapped_column(Text, default="{}")  # extra fields merged into job dict
    execution_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "content_job_id": self.content_job_id,
            "platform": self.platform,
            "device_id": self.device_id,
            "priority": self.priority,
            "priority_label": _PRIORITY_LABELS.get(self.priority, "NORMAL"),
            "scheduled_time": self.scheduled_time.isoformat() if self.scheduled_time else None,
            "schedule_expr": json.loads(self.schedule_expr) if self.schedule_expr else None,
            "depends_on_job_id": self.depends_on_job_id,
            "retry_max": self.retry_max,
            "retry_count": self.retry_count,
            "status": self.status,
            "job_config": json.loads(self.job_config_json or "{}"),
            "execution_job_id": self.execution_job_id,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── ExecutionQueue ────────────────────────────────────────────────────────────

class ExecutionQueue(Base):
    __tablename__ = "execution_queue"
    __table_args__ = (
        Index("ix_execution_queue_campaign_job_id", "campaign_job_id"),
        Index("ix_execution_queue_status", "status"),
        Index("ix_execution_queue_status_order", "status", "queue_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_job_id: Mapped[int] = mapped_column(Integer)
    queue_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(Text, default="WAITING")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_job_id": self.campaign_job_id,
            "queue_order": self.queue_order,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ── CampaignHistory ───────────────────────────────────────────────────────────

class CampaignHistory(Base):
    __tablename__ = "campaign_history"
    __table_args__ = (
        Index("ix_campaign_history_campaign_id", "campaign_id"),
        Index("ix_campaign_history_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(Text)      # DISPATCHED, COMPLETED, FAILED, RETRIED, PAUSED, etc.
    result: Mapped[str] = mapped_column(Text, default="OK")
    detail: Mapped[str] = mapped_column(Text, default="")
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_job_id": self.campaign_job_id,
            "campaign_id": self.campaign_id,
            "action": self.action,
            "result": self.result,
            "detail": self.detail,
            "duration_s": self.duration_s,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
