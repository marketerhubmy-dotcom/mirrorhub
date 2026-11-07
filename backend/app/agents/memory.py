"""
Agent Memory — thin wrapper around repository.remember / recall.

Provides domain-specific helpers that build structured memory keys
and values from execution data.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from . import repository as repo
from .models import (
    MEM_CAMPAIGN, MEM_DEVICE, MEM_PLUGIN, MEM_WORKFLOW,
    MEM_OPTIMIZATION, MEM_PROMPT, AgentMemoryEntry,
)

logger = logging.getLogger(__name__)


# ── Generic read/write ────────────────────────────────────────────────────────

async def remember(
    db: AsyncSession,
    key: str,
    category: str,
    value: dict,
    summary: str = "",
) -> AgentMemoryEntry:
    return await repo.remember(db, key, category, value, summary)


async def recall_all(db: AsyncSession, category: str | None = None) -> list[AgentMemoryEntry]:
    return await repo.recall(db, category=category)


async def recall_one(db: AsyncSession, key: str) -> AgentMemoryEntry | None:
    entries = await repo.recall(db, key=key)
    return entries[0] if entries else None


async def forget(db: AsyncSession, key: str) -> bool:
    return await repo.forget(db, key)


# ── Domain-specific writers ───────────────────────────────────────────────────

async def remember_campaign_result(
    db: AsyncSession,
    campaign_id: int,
    product: str,
    platform: str,
    total: int,
    completed: int,
    failed: int,
    avg_duration_s: float,
) -> None:
    key = f"campaign:{campaign_id}"
    value = {
        "campaign_id": campaign_id,
        "product": product,
        "platform": platform,
        "total": total,
        "completed": completed,
        "failed": failed,
        "success_rate": round(completed / max(total, 1) * 100, 1),
        "avg_duration_s": round(avg_duration_s, 1),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    summary = f"{platform} campaign {campaign_id}: {completed}/{total} completed ({value['success_rate']}%)"
    await remember(db, key, MEM_CAMPAIGN, value, summary)


async def remember_device_performance(
    db: AsyncSession,
    device_id: str,
    jobs_completed: int,
    jobs_failed: int,
    avg_latency_ms: float,
    performance_score: float,
) -> None:
    key = f"device:{device_id}"
    success_rate = round(jobs_completed / max(jobs_completed + jobs_failed, 1) * 100, 1)
    value = {
        "device_id": device_id,
        "jobs_completed": jobs_completed,
        "jobs_failed": jobs_failed,
        "success_rate": success_rate,
        "avg_latency_ms": avg_latency_ms,
        "performance_score": performance_score,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    summary = f"Device {device_id[:8]}: {success_rate}% success, score {performance_score:.1f}"
    await remember(db, key, MEM_DEVICE, value, summary)


async def remember_plugin_reliability(
    db: AsyncSession,
    plugin: str,
    success_count: int,
    failure_count: int,
    common_errors: list[str],
) -> None:
    key = f"plugin:{plugin}"
    rate = round(success_count / max(success_count + failure_count, 1) * 100, 1)
    value = {
        "plugin": plugin,
        "success_count": success_count,
        "failure_count": failure_count,
        "reliability_rate": rate,
        "common_errors": common_errors[:5],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    summary = f"Plugin {plugin}: {rate}% reliability"
    await remember(db, key, MEM_PLUGIN, value, summary)


async def remember_optimization(
    db: AsyncSession,
    key: str,
    recommendation: str,
    data: dict,
) -> None:
    value = {**data, "recommendation": recommendation, "recorded_at": datetime.now(timezone.utc).isoformat()}
    await remember(db, f"opt:{key}", MEM_OPTIMIZATION, value, recommendation)


async def remember_successful_prompt(
    db: AsyncSession,
    product: str,
    platform: str,
    prompt_snippet: str,
) -> None:
    key = f"prompt:{platform}:{product[:20].replace(' ', '_')}"
    value = {
        "product": product,
        "platform": platform,
        "prompt_snippet": prompt_snippet[:200],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    summary = f"Successful {platform} prompt for '{product}'"
    await remember(db, key, MEM_PROMPT, value, summary)


# ── Domain-specific readers ───────────────────────────────────────────────────

async def get_device_performance_summary(db: AsyncSession, device_id: str) -> dict:
    entry = await recall_one(db, f"device:{device_id}")
    if not entry:
        return {"device_id": device_id, "known": False}
    data = json.loads(entry.value_json)
    data["known"] = True
    return data


async def get_plugin_reliability(db: AsyncSession, plugin: str) -> dict:
    entry = await recall_one(db, f"plugin:{plugin}")
    if not entry:
        return {"plugin": plugin, "known": False, "reliability_rate": 100.0}
    data = json.loads(entry.value_json)
    data["known"] = True
    return data


async def get_optimization_history(db: AsyncSession) -> list[dict]:
    entries = await recall_all(db, category=MEM_OPTIMIZATION)
    return [json.loads(e.value_json) for e in entries]
