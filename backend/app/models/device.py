from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, func
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
    # ── Device Manager (Desktop V1) ───────────────────────────────────────────
    hw_serial: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # ro.serialno – stable identity across USB/WiFi
    model: Mapped[str] = mapped_column(String(64), default="")
    manufacturer: Mapped[str] = mapped_column(String(64), default="")
    android_version: Mapped[str] = mapped_column(String(16), default="")
    sdk: Mapped[int] = mapped_column(Integer, default=0)
    transport: Mapped[str] = mapped_column(String(16), default="")      # usb | wifi
    state: Mapped[str] = mapped_column(String(24), default="absent")    # online|offline|unauthorized|reconnecting|absent
    storage_total_mb: Mapped[int] = mapped_column(Integer, default=0)
    storage_free_mb: Mapped[int] = mapped_column(Integer, default=0)
    screen_w: Mapped[int] = mapped_column(Integer, default=0)
    screen_h: Mapped[int] = mapped_column(Integer, default=0)
    input_state: Mapped[str] = mapped_column(String(16), default="")      # ""|ok|blocked|unknown (OEM input injection)
    tags: Mapped[str] = mapped_column(Text, default="[]")               # JSON list[str]
    group_name: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_seen: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
