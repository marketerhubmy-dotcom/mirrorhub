import json
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class SavedProduct(Base):
    __tablename__ = "saved_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # URL stored as-is after normalization; used for duplicate detection
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), default="tiktok_shop")
    product_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    shop_name: Mapped[str] = mapped_column(String(256), default="")
    price: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image_filename: Mapped[str | None] = mapped_column(String(128), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    reference_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # JSON arrays
    key_benefits: Mapped[str] = mapped_column(Text, default="[]")
    pain_points: Mapped[str] = mapped_column(Text, default="[]")
    desires: Mapped[str] = mapped_column(Text, default="[]")
    triggers: Mapped[str] = mapped_column(Text, default="[]")
    common_pain_points: Mapped[str] = mapped_column(Text, default="[]")
    buying_motivations: Mapped[str] = mapped_column(Text, default="[]")
    suggested_content_angles: Mapped[str] = mapped_column(Text, default="[]")
    # AI-generated pipeline defaults
    target_audience: Mapped[str] = mapped_column(String(512), default="")
    target_audience_options: Mapped[str] = mapped_column(Text, default="[]")
    default_video_objective: Mapped[str] = mapped_column(String(512), default="")
    default_video_style: Mapped[str] = mapped_column(String(512), default="")
    tiktok_product_name: Mapped[str] = mapped_column(String(256), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="url")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "platform": self.platform or "tiktok_shop",
            "product_id": self.product_id,
            "shop_name": self.shop_name or "",
            "price": self.price or "",
            "description": self.description or "",
            "image_filename": self.image_filename,
            "image_url": self.image_url,
            "reference_image_path": self.reference_image_path,
            "key_benefits": json.loads(self.key_benefits or "[]"),
            "pain_points": json.loads(self.pain_points or "[]"),
            "desires": json.loads(self.desires or "[]"),
            "triggers": json.loads(self.triggers or "[]"),
            "common_pain_points": json.loads(self.common_pain_points or "[]"),
            "buying_motivations": json.loads(self.buying_motivations or "[]"),
            "suggested_content_angles": json.loads(self.suggested_content_angles or "[]"),
            "target_audience": self.target_audience or "",
            "target_audience_options": json.loads(self.target_audience_options or "[]"),
            "default_video_objective": self.default_video_objective or "",
            "default_video_style": self.default_video_style or "",
            "tiktok_product_name": self.tiktok_product_name or "",
            "source_type": self.source_type or "url",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
