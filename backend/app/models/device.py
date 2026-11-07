from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(128), nullable=False)
    battery: Mapped[int] = mapped_column(Integer, default=0)
    wifi: Mapped[bool] = mapped_column(Boolean, default=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    adb_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
