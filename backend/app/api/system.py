"""
System endpoints — version, health, settings.

GET /api/v1/system/about     — build info, version, plugin list
GET /api/v1/system/health    — detailed health check (DB, ADB, disk)
GET /api/v1/system/settings  — read-only view of current settings
"""
import os
from pathlib import Path

from fastapi import APIRouter

from app.core.config import settings
from app.utils.adb_path import ADB as ADB_PATH
from app.version import get_build_info

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/about")
async def about():
    """Full build and version information."""
    return get_build_info()


@router.get("/health")
async def health():
    """
    Detailed health check.

    Returns status for:
    - application (always OK if reachable)
    - database     (checks file exists and is readable)
    - adb          (checks adb.exe is present)
    - openai       (checks API key is configured)
    - disk         (checks remaining space in project directory)
    """
    info = get_build_info()
    db_ok = info["database"]["exists"]

    # Disk space (rough — same volume as the DB file)
    try:
        import shutil
        db_file_path = Path(settings.database_url.split("///")[-1])
        total, used, free = shutil.disk_usage(db_file_path.parent if db_file_path.parent.exists() else Path("."))
        disk_free_gb = round(free / (1024 ** 3), 2)
        disk_ok = disk_free_gb > 0.5
    except Exception:
        disk_free_gb = -1
        disk_ok = True

    return {
        "status": "ok",
        "checks": {
            "application": {"ok": True, "detail": "Running"},
            "database": {
                "ok": db_ok,
                "detail": f"{info['database']['size_bytes'] // 1024} KB" if db_ok else "Not found",
            },
            "adb": {
                "ok": ADB_PATH.exists(),
                "detail": str(ADB_PATH) if ADB_PATH.exists() else "adb.exe not found",
            },
            "openai": {
                "ok": bool(settings.openai_api_key),
                "detail": "Configured" if settings.openai_api_key else "OPENAI_API_KEY not set — AI features disabled",
            },
            "disk": {
                "ok": disk_ok,
                "detail": f"{disk_free_gb} GB free",
            },
        },
    }


@router.get("/settings")
async def get_settings():
    """
    Read-only view of the current application settings.
    API key values are masked for security.
    """
    def mask(v: str) -> str:
        if not v:
            return ""
        return v[:8] + "…" if len(v) > 8 else "***"

    return {
        "app_name": settings.app_name,
        "host": settings.host,
        "port": settings.port,
        "cors_origins": settings.cors_origins,
        "device_timeout": settings.device_timeout,
        "openai_api_key": mask(settings.openai_api_key),
        "openai_model": settings.openai_model,
        "openai_max_tokens": settings.openai_max_tokens,
        "vision_cache_ttl": settings.vision_cache_ttl,
        "vision_poll_interval": settings.vision_poll_interval,
        "vision_default_timeout": settings.vision_default_timeout,
        "campaign_poll_interval": settings.campaign_poll_interval,
        "campaign_retry_delay": settings.campaign_retry_delay,
        "log_level": settings.log_level,
    }


@router.get("/diagnostics")
async def diagnostics():
    """Environment self-check (adb, scrcpy server, data dir, disk, devices). See docs/TROUBLESHOOTING.md."""
    from app.services.diagnostics import run_checks, summarize
    checks = await run_checks()
    return {"overall": summarize(checks), "checks": checks}


@router.get("/data")
async def data_info():
    """Where user data lives + backups available (ADR-005)."""
    from app.core import data_migration, runtime_paths
    return {
        "data_dir": str(runtime_paths.data_dir()),
        "database": str(runtime_paths.db_path()),
        "backups": data_migration.list_backups(),
    }


@router.post("/backup")
async def create_backup():
    from app.core import data_migration
    try:
        p = data_migration.create_backup("manual")
    except data_migration.DataError as exc:
        from fastapi import HTTPException
        raise HTTPException(400, str(exc))
    return {"ok": True, "name": p.name}


@router.post("/restore/{name}")
async def stage_restore(name: str):
    """Stage a restore; it is applied at next start-up after a safety backup of the current DB."""
    from fastapi import HTTPException
    from app.core import data_migration
    try:
        info = data_migration.stage_restore(name)
    except data_migration.DataError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "staged": info, "message": "Tutup dan buka semula Mirrorhub untuk melengkapkan pemulihan."}
