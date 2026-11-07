import json
from datetime import datetime, timezone

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class ExecutionJob(Base):
    __tablename__ = "execution_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_job_id: Mapped[int | None] = mapped_column(nullable=True)
    device_id: Mapped[str] = mapped_column(Text)
    adb_address: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(Text, default="youtube_create")
    post_type: Mapped[str] = mapped_column(Text, default="draft")
    schedule_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_prompt: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="WAITING")
    current_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[float] = mapped_column(default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[str] = mapped_column(Text, default="[]")
    last_screenshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime | None] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content_job_id": self.content_job_id,
            "device_id": self.device_id,
            "adb_address": self.adb_address,
            "platform": self.platform,
            "post_type": self.post_type,
            "schedule_time": self.schedule_time,
            "video_prompt": self.video_prompt,
            "image_path": self.image_path,
            "status": self.status,
            "current_step": self.current_step,
            "progress": self.progress,
            "error": self.error,
            "logs": json.loads(self.logs or "[]"),
            "last_screenshot": self.last_screenshot,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
