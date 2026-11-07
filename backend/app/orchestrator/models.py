"""
Orchestrator DB models.

New tables — never modify existing ones:
  device_profiles        Extended per-device state + capabilities
  device_groups          Named groups (YouTube Devices, TikTok Devices…)
  device_group_members   M:N join between groups and device_ids
  orchestrator_assignments  Job-to-device assignment history
"""
import json
from datetime import datetime, timezone
from sqlalchemy import Text, Integer, Float, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


# ── Status constants ──────────────────────────────────────────────────────────

STATUS_OFFLINE       = "OFFLINE"
STATUS_ONLINE        = "ONLINE"
STATUS_IDLE          = "IDLE"
STATUS_BUSY          = "BUSY"
STATUS_PAUSED        = "PAUSED"
STATUS_RECOVERING    = "RECOVERING"
STATUS_DISCONNECTED  = "DISCONNECTED"
STATUS_MAINTENANCE   = "MAINTENANCE"

ALL_STATUSES = {
    STATUS_OFFLINE, STATUS_ONLINE, STATUS_IDLE, STATUS_BUSY,
    STATUS_PAUSED, STATUS_RECOVERING, STATUS_DISCONNECTED, STATUS_MAINTENANCE,
}

# Statuses that can accept a new job
AVAILABLE_STATUSES = {STATUS_IDLE, STATUS_ONLINE}


# ── DeviceProfile ─────────────────────────────────────────────────────────────

class DeviceProfile(Base):
    """
    Extended orchestrator state for a device.

    One row per device_id. Created lazily on first orchestrator access.
    References the `devices` table by device_id string (no FK to avoid
    modifying the existing schema).
    """
    __tablename__ = "device_profiles"
    __table_args__ = (
        Index("ix_device_profiles_status", "status"),
        Index("ix_device_profiles_group_id", "group_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    # Orchestrator state
    status: Mapped[str] = mapped_column(Text, default=STATUS_OFFLINE)
    priority: Mapped[int] = mapped_column(Integer, default=5)  # higher = preferred
    group_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    # Capabilities (populated by health monitor via ADB)
    resolution_w: Mapped[int] = mapped_column(Integer, default=1080)
    resolution_h: Mapped[int] = mapped_column(Integer, default=2400)
    android_version: Mapped[str] = mapped_column(Text, default="")
    ram_mb: Mapped[int] = mapped_column(Integer, default=0)
    storage_gb: Mapped[float] = mapped_column(Float, default=0.0)
    installed_apps: Mapped[str] = mapped_column(Text, default="[]")     # JSON list of package names
    supported_plugins: Mapped[str] = mapped_column(Text, default='["tiktok","youtube_create"]')

    # Health metrics (updated by monitor)
    performance_score: Mapped[float] = mapped_column(Float, default=5.0)  # 0.0–10.0
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    last_health_check: Mapped[datetime | None] = mapped_column(nullable=True)

    # Statistics
    total_jobs_completed: Mapped[int] = mapped_column(Integer, default=0)
    total_jobs_failed: Mapped[int] = mapped_column(Integer, default=0)
    last_job_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "status": self.status,
            "priority": self.priority,
            "group_id": self.group_id,
            "notes": self.notes,
            "capabilities": {
                "resolution": f"{self.resolution_w}x{self.resolution_h}",
                "android_version": self.android_version,
                "ram_mb": self.ram_mb,
                "storage_gb": self.storage_gb,
                "installed_apps": json.loads(self.installed_apps or "[]"),
                "supported_plugins": json.loads(self.supported_plugins or "[]"),
            },
            "health": {
                "performance_score": round(self.performance_score, 2),
                "latency_ms": round(self.latency_ms, 1),
                "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            },
            "stats": {
                "total_jobs_completed": self.total_jobs_completed,
                "total_jobs_failed": self.total_jobs_failed,
                "success_rate": round(
                    self.total_jobs_completed
                    / max(self.total_jobs_completed + self.total_jobs_failed, 1) * 100, 1
                ),
                "last_job_completed_at": (
                    self.last_job_completed_at.isoformat() if self.last_job_completed_at else None
                ),
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── DeviceGroup ───────────────────────────────────────────────────────────────

class DeviceGroup(Base):
    """Named group of devices (YouTube Devices, TikTok Devices, etc.)."""
    __tablename__ = "device_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    default_plugin: Mapped[str | None] = mapped_column(Text, nullable=True)  # "tiktok" | "youtube_create"
    default_strategy: Mapped[str] = mapped_column(Text, default="least_busy")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "default_plugin": self.default_plugin,
            "default_strategy": self.default_strategy,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── DeviceGroupMember ─────────────────────────────────────────────────────────

class DeviceGroupMember(Base):
    """M:N join — one row per (group_id, device_id) pair."""
    __tablename__ = "device_group_members"
    __table_args__ = (
        Index("ix_device_group_members_group_id", "group_id"),
        Index("ix_device_group_members_device_id", "device_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "device_id": self.device_id,
            "added_at": self.added_at.isoformat() if self.added_at else None,
        }


# ── OrchestratorAssignment ────────────────────────────────────────────────────

class OrchestratorAssignment(Base):
    """
    Audit record of every job-to-device assignment made by the orchestrator.

    Includes migrations (failover): status=MIGRATED, migrated_to=new_device_id.
    """
    __tablename__ = "orchestrator_assignments"
    __table_args__ = (
        Index("ix_orch_assign_campaign_job_id", "campaign_job_id"),
        Index("ix_orch_assign_device_id", "device_id"),
        Index("ix_orch_assign_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str] = mapped_column(Text, default="manual")  # balancing strategy used
    reason: Mapped[str] = mapped_column(Text, default="")          # human-readable explanation
    status: Mapped[str] = mapped_column(Text, default="ASSIGNED")  # ASSIGNED/RUNNING/COMPLETED/FAILED/MIGRATED
    migrated_to: Mapped[str | None] = mapped_column(Text, nullable=True)  # target device on migration
    assigned_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "campaign_job_id": self.campaign_job_id,
            "device_id": self.device_id,
            "strategy": self.strategy,
            "reason": self.reason,
            "status": self.status,
            "migrated_to": self.migrated_to,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
