"""
Shared ADB executable path resolver.

Every module that needs adb.exe should import from here instead of
computing the path inline. This keeps path logic in one place and
makes the project root relocatable.

Usage:
    from app.utils.adb_path import ADB

The ADB constant is an absolute Path object pointing to:
    <project_root>/tools/scrcpy/scrcpy-win64-v4.0/adb.exe
"""
from pathlib import Path

# Navigate from this file to the project root:
#   adb_path.py → utils/ → app/ → backend/ → project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

ADB: Path = _PROJECT_ROOT / "tools" / "scrcpy" / "scrcpy-win64-v4.0" / "adb.exe"
SCRCPY: Path = _PROJECT_ROOT / "tools" / "scrcpy" / "scrcpy-win64-v4.0" / "scrcpy.exe"
