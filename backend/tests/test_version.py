"""Tests for the version module."""
import pytest
from app.version import VERSION, VERSION_TUPLE, get_build_info


def test_version_format():
    parts = VERSION.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_version_tuple_matches_string():
    major, minor, patch = VERSION_TUPLE
    assert VERSION == f"{major}.{minor}.{patch}"


def test_build_info_keys():
    info = get_build_info()
    required = {"version", "release_name", "build_date", "python_version",
                "platform", "architecture", "plugins", "modules", "database", "server_time"}
    assert required.issubset(info.keys())


def test_build_info_database_has_required_fields():
    info = get_build_info()
    assert "path" in info["database"]
    assert "exists" in info["database"]
    assert "size_bytes" in info["database"]


def test_build_info_version_matches():
    info = get_build_info()
    assert info["version"] == VERSION
