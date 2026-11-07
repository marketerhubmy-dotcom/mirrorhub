"""Pydantic schemas for orchestrator API request/response."""
from pydantic import BaseModel, Field


class DeviceProfileUpdate(BaseModel):
    status: str | None = None
    priority: int | None = None
    group_id: int | None = None
    notes: str | None = None
    supported_plugins: list[str] | None = None
    resolution_w: int | None = None
    resolution_h: int | None = None
    android_version: str | None = None
    ram_mb: int | None = None
    storage_gb: float | None = None


class DeviceGroupCreate(BaseModel):
    name: str
    description: str = ""
    default_plugin: str | None = None
    default_strategy: str = "least_busy"


class DeviceGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    default_plugin: str | None = None
    default_strategy: str | None = None


class GroupMemberRequest(BaseModel):
    device_id: str


class DistributeRequest(BaseModel):
    strategy: str = "least_busy"       # round_robin | least_busy | fastest | priority_device | manual
    group_id: int | None = None        # restrict to devices in this group
    plugin_filter: str | None = None   # only devices that support this plugin


class MigrateRequest(BaseModel):
    from_device_id: str
    to_device_id: str
    job_statuses: list[str] = Field(default_factory=lambda: ["WAITING", "READY"])


class ReservationRequest(BaseModel):
    device_id: str
    reason: str = ""


class RebalanceRequest(BaseModel):
    campaign_id: int | None = None   # if None: rebalance entire queue
    strategy: str = "least_busy"
