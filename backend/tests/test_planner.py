"""Tests for campaign planner utility functions."""
import pytest
from unittest.mock import MagicMock
from app.campaign.planner import validate_dependencies


def _make_job(id, depends_on=None):
    j = MagicMock()
    j.id = id
    j.depends_on_job_id = depends_on
    return j


def test_no_dependencies_no_errors():
    jobs = [_make_job(1), _make_job(2), _make_job(3)]
    errors = validate_dependencies(jobs)
    assert errors == []


def test_simple_chain_no_circular():
    # 1 depends on 2, 2 depends on 3 — straight chain, valid
    jobs = [_make_job(1, depends_on=2), _make_job(2, depends_on=3), _make_job(3)]
    errors = validate_dependencies(jobs)
    assert errors == []


def test_circular_dependency_detected():
    # 1 → 2 → 1 (cycle)
    jobs = [_make_job(1, depends_on=2), _make_job(2, depends_on=1)]
    errors = validate_dependencies(jobs)
    assert len(errors) > 0
    assert any("Circular" in e for e in errors)


def test_self_dependency_detected():
    # Job depends on itself
    jobs = [_make_job(1, depends_on=1)]
    errors = validate_dependencies(jobs)
    assert len(errors) > 0


def test_three_node_cycle():
    # 1 → 2 → 3 → 1
    jobs = [_make_job(1, depends_on=2), _make_job(2, depends_on=3), _make_job(3, depends_on=1)]
    errors = validate_dependencies(jobs)
    assert len(errors) > 0
