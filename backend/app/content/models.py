import json
from datetime import datetime
from enum import Enum
from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class ContentStatus(str, Enum):
    IDEA = "IDEA"
    BRIEF = "BRIEF"
    PROMPT_READY = "PROMPT_READY"
    WAITING_GENERATION = "WAITING_GENERATION"
    VIDEO_CREATED = "VIDEO_CREATED"
    READY_TO_POST = "READY_TO_POST"
    POSTED = "POSTED"
    FAILED = "FAILED"


class ContentJob(Base):
    __tablename__ = "content_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    topic: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(Text, default="")
    product: Mapped[str] = mapped_column(Text, default="")
    duration: Mapped[str] = mapped_column(String(16), default="8s")
    visual_style: Mapped[str] = mapped_column(Text, default="")
    # AI-generated
    hook: Mapped[str] = mapped_column(Text, default="")
    story: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(Text, default="")
    video_prompt: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(Text, default="[]")        # JSON array
    reference_images: Mapped[str] = mapped_column(Text, default="[]")  # JSON array of filenames
    tiktok_product_name: Mapped[str] = mapped_column(Text, default="")
    publish_mode: Mapped[str] = mapped_column(String(16), default="manual")  # manual | auto | draft
    selected_product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON object
    avatar: Mapped[str] = mapped_column(Text, default="")             # avatar/character preset
    cover_hook: Mapped[str] = mapped_column(Text, default="")         # TikTok cover text (≤3 lines)
    custom_instructions: Mapped[str] = mapped_column(Text, default="")  # user freeform notes
    video_type: Mapped[str] = mapped_column(Text, default="")          # awareness | engagement | conversion | demo …
    selected_content_angle: Mapped[str] = mapped_column(Text, default="")  # chosen angle from product library
    status: Mapped[str] = mapped_column(String(32), default=ContentStatus.IDEA)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "topic": self.topic,
            "objective": self.objective,
            "audience": self.audience,
            "product": self.product,
            "duration": self.duration,
            "visual_style": self.visual_style,
            "hook": self.hook,
            "story": self.story,
            "cta": self.cta,
            "video_prompt": self.video_prompt,
            "caption": self.caption,
            "hashtags": json.loads(self.hashtags or "[]"),
            "reference_images": json.loads(self.reference_images or "[]"),
            "tiktok_product_name": self.tiktok_product_name or "",
            "publish_mode": self.publish_mode or "manual",
            "selected_product_id": self.selected_product_id,
            "product_snapshot": json.loads(self.product_snapshot) if self.product_snapshot else None,
            "avatar": self.avatar or "",
            "cover_hook": self.cover_hook or "",
            "custom_instructions": self.custom_instructions or "",
            "video_type": self.video_type or "",
            "selected_content_angle": self.selected_content_angle or "",
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
