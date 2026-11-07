from datetime import datetime
from pydantic import BaseModel


class CampaignCreate(BaseModel):
    name: str
    description: str = ""
    platform_default: str = "tiktok"
    device_id_default: str = ""
    timezone: str = "UTC"


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    platform_default: str | None = None
    device_id_default: str | None = None
    timezone: str | None = None
    status: str | None = None


class CampaignJobCreate(BaseModel):
    campaign_id: int
    content_job_id: int | None = None
    platform: str = "tiktok"
    device_id: str = ""
    priority: int = 2          # 0=critical 1=high 2=normal 3=low
    scheduled_time: datetime | None = None
    schedule_expr: dict | None = None    # e.g. {"type": "daily", "time": "09:00", "tz": "UTC"}
    depends_on_job_id: int | None = None
    retry_max: int = 3
    job_config: dict = {}


class CampaignJobUpdate(BaseModel):
    platform: str | None = None
    device_id: str | None = None
    priority: int | None = None
    scheduled_time: datetime | None = None
    schedule_expr: dict | None = None
    depends_on_job_id: int | None = None
    retry_max: int | None = None
    job_config: dict | None = None
    status: str | None = None


class CampaignStartRequest(BaseModel):
    simulate: bool = False


class QueueReorderRequest(BaseModel):
    campaign_job_id: int
    new_order: int
