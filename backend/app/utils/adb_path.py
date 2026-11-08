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
from app.core import runtime_paths

# Dev: repo root (4 parents up). Frozen: folder next to MirrorHub.exe.
# The traversal below is kept in runtime_paths.install_root():
#   parent.parent.parent.parent
_PROJECT_ROOT = runtime_paths.install_root()
_TOOLS = runtime_paths.tools_root() / "scrcpy" / "scrcpy-win64-v4.0"

ADB: Path = _TOOLS / "adb.exe"
SCRCPY: Path = _TOOLS / "scrcpy.exe"
