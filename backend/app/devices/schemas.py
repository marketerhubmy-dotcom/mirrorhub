from datetime import datetime
import json
from pydantic import BaseModel, field_validator


class DeviceRegisterRequest(BaseModel):
    device_id: str
    device_name: str
    battery: int = 0
    wifi: bool = True


class DeviceResponse(BaseModel):
    device_id: str
    device_name: str
    battery: int
    wifi: bool
    is_online: bool
    adb_address: str | None = None
    last_seen: datetime
    # Device Manager fields (all optional for backward compatibility)
    hw_serial: str | None = None
    model: str = ""
    manufacturer: str = ""
    android_version: str = ""
    sdk: int = 0
    transport: str = ""
    state: str = "absent"
    storage_total_mb: int = 0
    storage_free_mb: int = 0
    screen_w: int = 0
    screen_h: int = 0
    tags: list[str] = []
    group_name: str = ""
    notes: str = ""
    last_error: str = ""

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, v):
        if isinstance(v, str):
            try:
                v = json.loads(v or "[]")
            except json.JSONDecodeError:
                return []
        return v if isinstance(v, list) else []


class DeviceHeartbeat(BaseModel):
    device_id: str
    battery: int
    wifi: bool
