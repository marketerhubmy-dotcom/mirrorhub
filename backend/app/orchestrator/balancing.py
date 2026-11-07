"""
Load balancer strategies for picking a device from a pool.

All strategies accept a list of DeviceProfile and return one (or None).
"""
from __future__ import annotations

import itertools
import random
from typing import Callable

from .models import DeviceProfile


# ── Strategy implementations ──────────────────────────────────────────────────

def _round_robin(profiles: list[DeviceProfile], _ctx: dict) -> DeviceProfile | None:
    """
    Cycle through devices in insertion order.

    Uses a per-balancer counter stored in _ctx["rr_state"].
    """
    if not profiles:
        return None
    state = _ctx.setdefault("rr_state", {})
    cycle_key = ",".join(p.device_id for p in profiles)
    idx = state.get(cycle_key, 0) % len(profiles)
    state[cycle_key] = idx + 1
    return profiles[idx]


def _least_busy(profiles: list[DeviceProfile], _ctx: dict) -> DeviceProfile | None:
    """
    Return the device with the fewest in-flight jobs.

    Uses the `active_jobs` counter injected into _ctx by the caller.
    Falls back to highest performance_score for tie-breaking.
    """
    if not profiles:
        return None
    active: dict[str, int] = _ctx.get("active_jobs", {})
    return min(
        profiles,
        key=lambda p: (active.get(p.device_id, 0), -p.performance_score),
    )


def _fastest(profiles: list[DeviceProfile], _ctx: dict) -> DeviceProfile | None:
    """Return the device with the lowest latency_ms (excluding 0=unknown)."""
    if not profiles:
        return None
    known = [p for p in profiles if p.latency_ms > 0]
    if not known:
        return profiles[0]
    return min(known, key=lambda p: p.latency_ms)


def _priority_device(profiles: list[DeviceProfile], _ctx: dict) -> DeviceProfile | None:
    """Return the device with the highest priority value."""
    if not profiles:
        return None
    return max(profiles, key=lambda p: (p.priority, p.performance_score))


def _manual(profiles: list[DeviceProfile], _ctx: dict) -> DeviceProfile | None:
    """
    Pick the device_id explicitly named in _ctx["manual_device_id"].

    Falls back to least_busy if the named device is not in the pool.
    """
    target = _ctx.get("manual_device_id")
    if target:
        for p in profiles:
            if p.device_id == target:
                return p
    return _least_busy(profiles, _ctx)


# ── Registry ──────────────────────────────────────────────────────────────────

_STRATEGIES: dict[str, Callable[[list[DeviceProfile], dict], DeviceProfile | None]] = {
    "round_robin":     _round_robin,
    "least_busy":      _least_busy,
    "fastest":         _fastest,
    "priority_device": _priority_device,
    "manual":          _manual,
}

STRATEGY_NAMES = list(_STRATEGIES.keys())


# ── LoadBalancer ─────────────────────────────────────────────────────────────

class LoadBalancer:
    """
    Picks a device from an available pool using a chosen strategy.

    Thread-safety: the `_ctx` dict is per-instance mutable state.
    The monitor/manager owns one LoadBalancer instance and calls it
    from a single asyncio task, so no locking is needed.
    """

    def __init__(self, strategy: str = "least_busy") -> None:
        self.strategy = strategy if strategy in _STRATEGIES else "least_busy"
        self._ctx: dict = {}

    def pick(
        self,
        profiles: list[DeviceProfile],
        *,
        active_jobs: dict[str, int] | None = None,
        manual_device_id: str | None = None,
    ) -> DeviceProfile | None:
        """
        Select one DeviceProfile from `profiles`.

        Parameters
        ----------
        active_jobs:
            {device_id: count} of currently running jobs — used by least_busy.
        manual_device_id:
            Target device for the "manual" strategy.
        """
        self._ctx["active_jobs"] = active_jobs or {}
        if manual_device_id:
            self._ctx["manual_device_id"] = manual_device_id

        fn = _STRATEGIES[self.strategy]
        return fn(profiles, self._ctx)

    def set_strategy(self, strategy: str) -> None:
        if strategy not in _STRATEGIES:
            raise ValueError(f"Unknown strategy '{strategy}'. Valid: {STRATEGY_NAMES}")
        self.strategy = strategy
        self._ctx = {}  # reset per-strategy state

    def distribute(
        self,
        profiles: list[DeviceProfile],
        job_count: int,
        *,
        active_jobs: dict[str, int] | None = None,
    ) -> list[tuple[DeviceProfile, int]]:
        """
        Distribute `job_count` jobs across `profiles` using the current strategy.

        Returns a list of (profile, allocated_count) sorted by device priority.
        Uses the current strategy to build weights.
        """
        if not profiles or job_count <= 0:
            return []

        # Build weight for each device based on strategy-specific logic
        weights: list[float] = []
        for p in profiles:
            if self.strategy == "least_busy":
                active = (active_jobs or {}).get(p.device_id, 0)
                w = max(0.1, p.performance_score - active)
            elif self.strategy == "priority_device":
                w = float(p.priority)
            elif self.strategy == "fastest":
                w = 1.0 / max(p.latency_ms, 1.0)
            else:
                w = 1.0  # equal for round_robin and manual
            weights.append(w)

        total_weight = sum(weights)
        allocations: list[int] = []
        for w in weights:
            alloc = round(job_count * w / total_weight)
            allocations.append(alloc)

        # Fix rounding drift
        diff = job_count - sum(allocations)
        if diff != 0:
            # Give remainder to highest-weight device
            idx = weights.index(max(weights))
            allocations[idx] += diff

        return [(p, n) for p, n in zip(profiles, allocations) if n > 0]
