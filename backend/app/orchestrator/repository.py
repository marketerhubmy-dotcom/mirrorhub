"""DB CRUD helpers for the Orchestrator module."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    DeviceProfile, DeviceGroup, DeviceGroupMember,
    OrchestratorAssignment, STATUS_OFFLINE, AVAILABLE_STATUSES,
)
from .schemas import DeviceGroupCreate, DeviceGroupUpdate, DeviceProfileUpdate


# ── DeviceProfile ─────────────────────────────────────────────────────────────

async def get_profile(db: AsyncSession, device_id: str) -> DeviceProfile | None:
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.device_id == device_id)
    )
    return result.scalar_one_or_none()


async def get_or_create_profile(db: AsyncSession, device_id: str) -> DeviceProfile:
    """Lazily create a DeviceProfile if one doesn't exist yet."""
    profile = await get_profile(db, device_id)
    if not profile:
        profile = DeviceProfile(device_id=device_id, status=STATUS_OFFLINE)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


async def list_profiles(db: AsyncSession) -> list[DeviceProfile]:
    result = await db.execute(select(DeviceProfile).order_by(DeviceProfile.priority.desc()))
    return list(result.scalars().all())


async def list_available_profiles(
    db: AsyncSession,
    plugin: str | None = None,
    group_id: int | None = None,
) -> list[DeviceProfile]:
    """Return profiles in AVAILABLE_STATUSES, optionally filtered."""
    q = select(DeviceProfile).where(DeviceProfile.status.in_(AVAILABLE_STATUSES))
    if group_id is not None:
        member_ids_q = select(DeviceGroupMember.device_id).where(
            DeviceGroupMember.group_id == group_id
        )
        q = q.where(DeviceProfile.device_id.in_(member_ids_q))
    result = await db.execute(q.order_by(DeviceProfile.priority.desc()))
    profiles = list(result.scalars().all())
    if plugin:
        profiles = [p for p in profiles if plugin in (p.supported_plugins or "")]
    return profiles


async def update_profile(
    db: AsyncSession, device_id: str, data: DeviceProfileUpdate
) -> DeviceProfile | None:
    profile = await get_or_create_profile(db, device_id)
    for k, v in data.model_dump(exclude_none=True).items():
        if k == "supported_plugins" and isinstance(v, list):
            import json
            setattr(profile, k, json.dumps(v))
        else:
            setattr(profile, k, v)
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile)
    return profile


async def update_profile_status(
    db: AsyncSession, device_id: str, status: str
) -> DeviceProfile:
    profile = await get_or_create_profile(db, device_id)
    profile.status = status
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return profile


async def update_health_metrics(
    db: AsyncSession,
    device_id: str,
    latency_ms: float,
    performance_score: float,
    resolution_w: int = 0,
    resolution_h: int = 0,
    android_version: str = "",
    ram_mb: int = 0,
    storage_gb: float = 0.0,
) -> DeviceProfile:
    profile = await get_or_create_profile(db, device_id)
    profile.latency_ms = latency_ms
    profile.performance_score = performance_score
    profile.last_health_check = datetime.now(timezone.utc)
    if resolution_w:
        profile.resolution_w = resolution_w
    if resolution_h:
        profile.resolution_h = resolution_h
    if android_version:
        profile.android_version = android_version
    if ram_mb:
        profile.ram_mb = ram_mb
    if storage_gb:
        profile.storage_gb = storage_gb
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return profile


async def increment_job_stats(
    db: AsyncSession, device_id: str, success: bool
) -> None:
    profile = await get_or_create_profile(db, device_id)
    if success:
        profile.total_jobs_completed = (profile.total_jobs_completed or 0) + 1
        profile.last_job_completed_at = datetime.now(timezone.utc)
    else:
        profile.total_jobs_failed = (profile.total_jobs_failed or 0) + 1
    # Recompute performance score influence from success rate
    total = profile.total_jobs_completed + profile.total_jobs_failed
    if total > 0:
        sr = profile.total_jobs_completed / total
        # Blend historical SR with existing score (70% history, 30% current)
        profile.performance_score = min(10.0, round(sr * 10 * 0.7 + profile.performance_score * 0.3, 2))
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()


# ── DeviceGroup ───────────────────────────────────────────────────────────────

async def create_group(db: AsyncSession, data: DeviceGroupCreate) -> DeviceGroup:
    g = DeviceGroup(
        name=data.name,
        description=data.description,
        default_plugin=data.default_plugin,
        default_strategy=data.default_strategy,
    )
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return g


async def get_group(db: AsyncSession, group_id: int) -> DeviceGroup | None:
    return await db.get(DeviceGroup, group_id)


async def list_groups(db: AsyncSession) -> list[DeviceGroup]:
    result = await db.execute(select(DeviceGroup).order_by(DeviceGroup.name))
    return list(result.scalars().all())


async def update_group(
    db: AsyncSession, group_id: int, data: DeviceGroupUpdate
) -> DeviceGroup | None:
    g = await db.get(DeviceGroup, group_id)
    if not g:
        return None
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(g, k, v)
    g.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(g)
    return g


async def delete_group(db: AsyncSession, group_id: int) -> bool:
    g = await db.get(DeviceGroup, group_id)
    if not g:
        return False
    await db.delete(g)
    await db.commit()
    return True


async def add_member(db: AsyncSession, group_id: int, device_id: str) -> DeviceGroupMember:
    # Idempotent — don't add duplicates
    result = await db.execute(
        select(DeviceGroupMember).where(
            DeviceGroupMember.group_id == group_id,
            DeviceGroupMember.device_id == device_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    m = DeviceGroupMember(group_id=group_id, device_id=device_id)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


async def remove_member(db: AsyncSession, group_id: int, device_id: str) -> bool:
    result = await db.execute(
        select(DeviceGroupMember).where(
            DeviceGroupMember.group_id == group_id,
            DeviceGroupMember.device_id == device_id,
        )
    )
    m = result.scalar_one_or_none()
    if not m:
        return False
    await db.delete(m)
    await db.commit()
    return True


async def list_group_members(db: AsyncSession, group_id: int) -> list[DeviceGroupMember]:
    result = await db.execute(
        select(DeviceGroupMember).where(DeviceGroupMember.group_id == group_id)
    )
    return list(result.scalars().all())


# ── OrchestratorAssignment ────────────────────────────────────────────────────

async def record_assignment(
    db: AsyncSession,
    campaign_job_id: int,
    device_id: str,
    strategy: str,
    reason: str = "",
) -> OrchestratorAssignment:
    a = OrchestratorAssignment(
        campaign_job_id=campaign_job_id,
        device_id=device_id,
        strategy=strategy,
        reason=reason,
        status="ASSIGNED",
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


async def record_migration(
    db: AsyncSession,
    campaign_job_id: int,
    from_device_id: str,
    to_device_id: str,
    reason: str = "failover",
) -> OrchestratorAssignment:
    a = OrchestratorAssignment(
        campaign_job_id=campaign_job_id,
        device_id=from_device_id,
        strategy="failover",
        reason=reason,
        status="MIGRATED",
        migrated_to=to_device_id,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


async def list_assignments(
    db: AsyncSession,
    device_id: str | None = None,
    limit: int = 100,
) -> list[OrchestratorAssignment]:
    q = select(OrchestratorAssignment).order_by(
        OrchestratorAssignment.assigned_at.desc()
    ).limit(limit)
    if device_id:
        q = q.where(OrchestratorAssignment.device_id == device_id)
    result = await db.execute(q)
    return list(result.scalars().all())
