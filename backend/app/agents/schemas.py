"""Pydantic schemas for the Agent Layer API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class GoalSubmit(BaseModel):
    """POST /agents/goals body."""
    goal_text: str = Field(..., min_length=5)
    platform: str = "tiktok"         # tiktok | youtube_create
    product: str = ""
    target_count: int = Field(default=1, ge=1, le=500)
    priority: int = Field(default=2, ge=0, le=3)   # 0=critical 1=high 2=normal 3=low
    audience: str = ""
    visual_style: str = ""


class GoalUpdate(BaseModel):
    goal_text: str | None = None
    priority: int | None = None


class RecoverRequest(BaseModel):
    campaign_job_id: int
    action: str = "auto"  # auto | retry | reassign | pause | abort


class ForgetRequest(BaseModel):
    key: str
