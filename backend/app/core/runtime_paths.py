"""
Central, frozen-aware filesystem locations (ADR-005).

Two roots:

* install root  – read-only application files (frontend/dist, tools/adb, scrcpy).
                  Dev: the repository root.  Frozen (PyInstaller): the folder
                  containing MirrorHub.exe.
* data dir      – everything the user creates (database, uploads, logs,
                  backups, .env).  Always ``%APPDATA%\\Mirrorhub`` unless
                  ``MIRRORHUB_DATA_DIR`` is set.  Never inside Program Files.

Nothing here deletes or moves user data.  Legacy data that lives next to the
source tree (``backend/mirrorhub.db`` ...) is *copied* once by
``app.core.data_migration``; the original stays in place and acts as rollback.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "Mirrorhub"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_root() -> Path:
    """Folder that holds ``tools/`` and (for installs) the exe."""
    override = os.environ.get("MIRRORHUB_INSTALL_ROOT")
    if override:
        return Path(override)
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # runtime_paths.py → core/ → app/ → backend/ → project root
    return Path(__file__).parent.parent.parent.parent


def bundle_root() -> Path:
    """Where PyInstaller unpacked bundled data (frontend/dist). Dev: repo root."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", install_root()))
    return install_root()


def legacy_backend_dir() -> Path:
    """Pre-ADR-005 data location (``backend/``). Only meaningful in a source tree."""
    return Path(__file__).parent.parent.parent


def data_dir() -> Path:
    override = os.environ.get("MIRRORHUB_DATA_DIR")
    if override:
        base = Path(override)
    else:
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) / APP_DIR_NAME if appdata else Path.home() / f".{APP_DIR_NAME.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def uploads_dir() -> Path:
    return _sub("uploads")


def logs_dir() -> Path:
    return _sub("logs")


def backups_dir() -> Path:
    return _sub("backups")


def db_path() -> Path:
    return data_dir() / "mirrorhub.db"


def env_file() -> Path:
    return data_dir() / ".env"


def frontend_dist() -> Path:
    """Built React app. Frozen: bundled; dev: ``frontend/dist``."""
    if is_frozen():
        return bundle_root() / "frontend" / "dist"
    return install_root() / "frontend" / "dist"


def tools_root() -> Path:
    """Parent of bundled third-party binaries (see app.utils.adb_path)."""
    return install_root() / "tools"


def sqlite_url() -> str:
    return f"sqlite+aiosqlite:///{db_path().as_posix()}"
