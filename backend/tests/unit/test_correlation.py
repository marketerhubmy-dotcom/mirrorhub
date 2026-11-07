"""
Tests for the correlation ID utility (app.utils.correlation).

Verifies:
  1. new_correlation_id() returns a non-empty string and stores it in context.
  2. get_correlation_id() returns the same ID in the same async context.
  3. IDs are isolated between different asyncio tasks.
  4. set_correlation_id() allows overriding the current ID.
  5. correlation_id_for() builds a scoped ID.
  6. Default value (no ID set) is an empty string, not None.
"""
import asyncio

import pytest

from app.utils.correlation import (
    new_correlation_id,
    set_correlation_id,
    get_correlation_id,
    correlation_id_for,
)


def test_new_correlation_id_returns_string():
    cid = new_correlation_id()
    assert isinstance(cid, str)
    assert len(cid) == 8


def test_get_returns_same_as_new():
    cid = new_correlation_id()
    assert get_correlation_id() == cid


def test_set_then_get():
    set_correlation_id("custom-id")
    assert get_correlation_id() == "custom-id"


def test_default_is_empty_string():
    # Clear any leftover state
    set_correlation_id("")
    assert get_correlation_id() == ""


def test_correlation_id_for_int():
    cid = correlation_id_for("job", 42)
    assert cid.startswith("job-")
    assert get_correlation_id() == cid


def test_correlation_id_for_str():
    cid = correlation_id_for("campaign", "abc")
    assert cid == "campaign-abc"


@pytest.mark.asyncio
async def test_ids_isolated_between_tasks():
    """
    Each asyncio task should have its own correlation ID context.
    Task A's ID must not bleed into Task B's context.
    """
    results: dict[str, str] = {}

    async def task_a():
        new_correlation_id()
        set_correlation_id("aaa-aaaa")
        await asyncio.sleep(0)     # yield control
        results["a"] = get_correlation_id()

    async def task_b():
        # task_b never sets a correlation ID
        results["b"] = get_correlation_id()

    await asyncio.gather(task_a(), task_b())

    assert results["a"] == "aaa-aaaa"
    # task_b inherits the context from its creator (the test function),
    # not from task_a — so it should NOT see task_a's ID.
    assert results["b"] != "aaa-aaaa"


@pytest.mark.asyncio
async def test_new_generates_unique_ids():
    ids = set()
    for _ in range(100):
        ids.add(new_correlation_id())
    assert len(ids) == 100, "Expected 100 unique correlation IDs"
