"""
Orchestrator REST API.

Prefix: /api/v1/orchestrator
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from .manager import orchestrator
from .repository import (
    get_or_create_profile,
    list_profiles,
    update_profile,
    create_group,
    get_group,
    list_groups,
    update_group,
    delete_group,
    add_member,
    remove_member,
    list_group_members,
    list_assignments,
)
from .schemas import (
    DeviceProfileUpdate,
    DeviceGroupCreate,
    DeviceGroupUpdate,
    GroupMemberRequest,
    DistributeRequest,
    MigrateRequest,
    ReservationRequest,
    RebalanceRequest,
)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


# ── Fleet ─────────────────────────────────────────────────────────────────────

@router.get("/fleet")
async def get_fleet(db: AsyncSession = Depends(get_db)) -> dict:
    return await orchestrator.get_fleet_status(db)


@router.get("/fleet/stats")
async def fleet_stats(db: AsyncSession = Depends(get_db)) -> dict:
    return await orchestrator.get_stats(db)


# ── Device profiles ───────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(db: AsyncSession = Depends(get_db)) -> list[dict]:
    profiles = await list_profiles(db)
    return [p.to_dict() for p in profiles]


@router.get("/devices/{device_id}")
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    profile = await get_or_create_profile(db, device_id)
    return profile.to_dict()


@router.patch("/devices/{device_id}")
async def patch_device(
    device_id: str,
    data: DeviceProfileUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile = await update_profile(db, device_id, data)
    if not profile:
        raise HTTPException(404, "Device not found")
    return profile.to_dict()


@router.get("/devices/{device_id}/stats")
async def device_stats(device_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    return await orchestrator.get_stats(db, device_id=device_id)


@router.get("/devices/{device_id}/assignments")
async def device_assignments(
    device_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await list_assignments(db, device_id=device_id, limit=limit)
    return [r.to_dict() for r in rows]


# ── Maintenance / reservation ─────────────────────────────────────────────────

@router.post("/devices/{device_id}/maintenance")
async def set_maintenance(
    device_id: str,
    req: ReservationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await orchestrator.set_device_maintenance(db, device_id, reason=req.reason)


@router.post("/devices/{device_id}/release")
async def release_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await orchestrator.release_device(db, device_id)


@router.post("/devices/{device_id}/reserve")
async def reserve_device(
    device_id: str,
    req: ReservationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await orchestrator.reserve_device(db, device_id, reason=req.reason)


# ── Groups ────────────────────────────────────────────────────────────────────

@router.get("/groups")
async def list_all_groups(db: AsyncSession = Depends(get_db)) -> list[dict]:
    groups = await list_groups(db)
    return [g.to_dict() for g in groups]


@router.post("/groups", status_code=201)
async def create_new_group(
    data: DeviceGroupCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    g = await create_group(db, data)
    return g.to_dict()


@router.get("/groups/{group_id}")
async def get_one_group(group_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    g = await get_group(db, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    return g.to_dict()


@router.patch("/groups/{group_id}")
async def patch_group(
    group_id: int,
    data: DeviceGroupUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    g = await update_group(db, group_id, data)
    if not g:
        raise HTTPException(404, "Group not found")
    return g.to_dict()


@router.delete("/groups/{group_id}", status_code=204)
async def delete_one_group(group_id: int, db: AsyncSession = Depends(get_db)) -> None:
    ok = await delete_group(db, group_id)
    if not ok:
        raise HTTPException(404, "Group not found")


@router.get("/groups/{group_id}/members")
async def group_members(group_id: int, db: AsyncSession = Depends(get_db)) -> list[dict]:
    members = await list_group_members(db, group_id)
    return [m.to_dict() for m in members]


@router.post("/groups/{group_id}/members", status_code=201)
async def add_group_member(
    group_id: int,
    req: GroupMemberRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    m = await add_member(db, group_id, req.device_id)
    return m.to_dict()


@router.delete("/groups/{group_id}/members/{device_id}", status_code=204)
async def remove_group_member(
    group_id: int,
    device_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    ok = await remove_member(db, group_id, device_id)
    if not ok:
        raise HTTPException(404, "Member not found")


# ── Distribution / allocation ─────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/distribute")
async def distribute(
    campaign_id: int,
    req: DistributeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    counts = await orchestrator.auto_distribute(
        db,
        campaign_id,
        strategy=req.strategy,
        group_id=req.group_id,
        plugin_filter=req.plugin_filter,
    )
    return {"campaign_id": campaign_id, "distribution": counts}


@router.post("/rebalance")
async def rebalance(
    req: RebalanceRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await orchestrator.rebalance(
        db, campaign_id=req.campaign_id, strategy=req.strategy
    )


@router.post("/migrate")
async def migrate(
    req: MigrateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await orchestrator.migrate(
        db, req.from_device_id, req.to_device_id, req.job_statuses
    )
