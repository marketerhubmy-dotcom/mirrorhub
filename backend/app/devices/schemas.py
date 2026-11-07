from datetime import datetime
from pydantic import BaseModel


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

    model_config = {"from_attributes": True}


class DeviceHeartbeat(BaseModel):
    device_id: str
    battery: int
    wifi: bool
