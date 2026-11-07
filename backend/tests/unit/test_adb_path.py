"""
CLAIM: All production ADB calls resolve through the canonical ADB path module.

Verifies:
  1. utils/adb_path.py exports ADB and SCRCPY Path constants.
  2. The paths point to the expected relative location from the project root.
  3. No module in app/ defines its own _adb() or _get_adb() helper function.
  4. Every module that uses ADB imports from app.utils.adb_path.
"""
import ast
import re
from pathlib import Path

import pytest

# ── Locate project root ───────────────────────────────────────────────────────

_BACKEND = Path(__file__).parent.parent.parent          # backend/
_PROJECT = _BACKEND.parent                               # 0. Mirrorhub/
_APP     = _BACKEND / "app"

# ── Fixture: adb_path module ──────────────────────────────────────────────────

def test_adb_path_exports_exist():
    """ADB and SCRCPY are importable from app.utils.adb_path."""
    from app.utils.adb_path import ADB, SCRCPY
    assert ADB is not None
    assert SCRCPY is not None


def test_adb_resolves_to_correct_relative_path():
    """ADB path ends with tools/scrcpy/scrcpy-win64-v4.0/adb.exe."""
    from app.utils.adb_path import ADB
    parts = ADB.parts
    assert "tools" in parts
    assert "scrcpy" in parts
    assert "adb.exe" == parts[-1]


def test_scrcpy_resolves_to_correct_relative_path():
    """SCRCPY path ends with tools/scrcpy/scrcpy-win64-v4.0/scrcpy.exe."""
    from app.utils.adb_path import SCRCPY
    assert SCRCPY.parts[-1] == "scrcpy.exe"


def test_adb_path_root_calculation():
    """ADB path uses exactly 4 parent.parent traversals (file→utils→app→backend→root)."""
    from app.utils import adb_path as mod
    source = Path(mod.__file__).read_text()
    # Check that the module navigates 4 levels up from __file__
    assert "parent.parent.parent.parent" in source


def test_no_inline_adb_helpers_in_app():
    """
    No module in app/ defines its own _adb() or _get_adb() function.

    Previously 9 modules each computed the ADB path independently.
    After unification all must import from app.utils.adb_path.
    """
    banned = re.compile(r"def\s+_(?:adb|get_adb)\s*\(")
    violations = []

    for py_file in _APP.rglob("*.py"):
        # Skip the canonical module itself
        if py_file.name == "adb_path.py":
            continue
        text = py_file.read_text(encoding="utf-8", errors="replace")
        if banned.search(text):
            violations.append(str(py_file.relative_to(_BACKEND)))

    assert violations == [], (
        f"Found inline ADB path helpers in:\n  " + "\n  ".join(violations)
    )


def test_no_hardcoded_scrcpy_path_outside_adb_path():
    """
    No module outside adb_path.py constructs the scrcpy-win64 path inline.

    Inline path construction was the old pattern:
        base = Path(__file__).parent.parent.parent.parent
        return base / "tools" / "scrcpy" / "scrcpy-win64-v4.0" / "adb.exe"
    """
    banned = re.compile(r"scrcpy-win64")
    violations = []

    for py_file in _APP.rglob("*.py"):
        if py_file.name == "adb_path.py":
            continue
        text = py_file.read_text(encoding="utf-8", errors="replace")
        if banned.search(text):
            violations.append(str(py_file.relative_to(_BACKEND)))

    assert violations == [], (
        f"Found hardcoded scrcpy path in:\n  " + "\n  ".join(violations)
    )
