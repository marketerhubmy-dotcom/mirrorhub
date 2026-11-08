"""
User-data migration, backup and rollback (ADR-005).

Rules (never violated by this module):
  * the legacy database / uploads are only ever COPIED, never moved or deleted;
  * every database replacement is preceded by a verified backup;
  * a restore is *staged* and applied at the next start-up, before the engine
    opens the file, so a running process never has its DB swapped underneath it.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.core import runtime_paths as rp

logger = logging.getLogger(__name__)

MIGRATION_MARKER = "migration.json"
PENDING_RESTORE = "restore.pending.json"
_SAFE_NAME = __import__("re").compile(r"^[A-Za-z0-9._-]{1,128}\.db$")


class DataError(Exception):
    """Raised for user-facing backup/restore problems."""


# ── helpers ───────────────────────────────────────────────────────────────────

def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def sqlite_copy(src: Path, dst: Path) -> None:
    """Consistent copy using SQLite's online backup API (safe on live WAL DBs)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise DataError(f"refusing to overwrite existing file: {dst}")
    s = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        d = sqlite3.connect(str(dst))
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def integrity_ok(path: Path) -> bool:
    try:
        c = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            row = c.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            c.close()
    except sqlite3.Error:
        return False


# ── legacy → AppData migration ────────────────────────────────────────────────

def migrate_legacy_data(legacy_dir: Path | None = None) -> dict:
    """
    Copy ``<legacy>/mirrorhub.db`` and ``<legacy>/uploads`` into the data dir
    once.  Idempotent: does nothing when the new DB exists or already migrated.
    Returns a report dict (also persisted to ``migration.json``).
    """
    legacy = legacy_dir or rp.legacy_backend_dir()
    data = rp.data_dir()
    marker = data / MIGRATION_MARKER
    report: dict = {"status": "skipped", "reason": "", "legacy": str(legacy)}

    if marker.exists():
        report["reason"] = "already migrated"
        return report

    new_db = rp.db_path()
    old_db = legacy / "mirrorhub.db"
    if legacy.resolve() == data.resolve():
        report["reason"] = "legacy dir is the data dir"
        return report

    if new_db.exists():
        report["reason"] = "new database already exists; legacy left untouched"
        return report

    if old_db.exists() and old_db.stat().st_size > 0:
        if not integrity_ok(old_db):
            report.update(status="failed", reason="legacy database failed integrity_check; not copied")
            logger.error("Legacy DB %s failed integrity_check — migration aborted", old_db)
            return report
        try:
            sqlite_copy(old_db, new_db)
        except (DataError, sqlite3.Error, OSError) as exc:
            if new_db.exists():
                new_db.unlink()  # partial copy of OUR new file only
            report.update(status="failed", reason=f"copy failed: {exc}")
            logger.error("Legacy DB copy failed: %s", exc)
            return report
        if not integrity_ok(new_db):
            new_db.unlink()
            report.update(status="failed", reason="copied database failed integrity_check")
            return report
        # keep a pristine copy of what we imported, for rollback
        backup = rp.backups_dir() / f"mirrorhub_{_stamp()}_pre-migration.db"
        shutil.copy2(new_db, backup)
        report.update(status="migrated", db=str(new_db), backup=str(backup))
    else:
        report.update(status="fresh", reason="no legacy database")

    up_old = legacy / "uploads"
    if up_old.is_dir():
        copied = 0
        for f in up_old.rglob("*"):
            if f.is_file():
                target = rp.uploads_dir() / f.relative_to(up_old)
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    copied += 1
        report["uploads_copied"] = copied

    report["at"] = datetime.now().isoformat(timespec="seconds")
    marker.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Data migration: %s", report)
    return report


# ── backups ───────────────────────────────────────────────────────────────────

def create_backup(label: str = "manual") -> Path:
    src = rp.db_path()
    if not src.exists():
        raise DataError("database does not exist yet")
    safe = "".join(c for c in label if c.isalnum() or c in "-_")[:32] or "manual"
    dst = rp.backups_dir() / f"mirrorhub_{_stamp()}_{safe}.db"
    sqlite_copy(src, dst)
    if not integrity_ok(dst):
        dst.unlink()
        raise DataError("backup failed integrity_check")
    logger.info("Backup created: %s", dst)
    return dst


def list_backups() -> list[dict]:
    out = []
    for f in sorted(rp.backups_dir().glob("*.db"), reverse=True):
        st = f.stat()
        out.append({
            "name": f.name,
            "size": st.st_size,
            "created": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        })
    return out


def _resolve_backup(name: str) -> Path:
    if not _SAFE_NAME.match(name or ""):
        raise DataError("invalid backup name")
    p = rp.backups_dir() / name
    if not p.is_file():
        raise DataError("backup not found")
    return p


def stage_restore(name: str) -> dict:
    """Validate a backup and schedule it to be applied at next start-up."""
    p = _resolve_backup(name)
    if not integrity_ok(p):
        raise DataError("selected backup failed integrity_check")
    info = {"name": name, "staged_at": datetime.now().isoformat(timespec="seconds")}
    (rp.data_dir() / PENDING_RESTORE).write_text(json.dumps(info), encoding="utf-8")
    return info


def cancel_staged_restore() -> bool:
    f = rp.data_dir() / PENDING_RESTORE
    if f.exists():
        f.unlink()
        return True
    return False


def apply_pending_restore() -> dict | None:
    """Call at start-up BEFORE the DB engine touches the file."""
    flag = rp.data_dir() / PENDING_RESTORE
    if not flag.exists():
        return None
    try:
        name = json.loads(flag.read_text(encoding="utf-8"))["name"]
        src = _resolve_backup(name)
        if not integrity_ok(src):
            raise DataError("staged backup failed integrity_check")
        db = rp.db_path()
        safety = None
        if db.exists():
            safety = rp.backups_dir() / f"mirrorhub_{_stamp()}_pre-restore.db"
            sqlite_copy(db, safety)
        tmp = db.with_suffix(".restoring")
        shutil.copy2(src, tmp)
        for ext in ("-wal", "-shm"):
            side = Path(str(db) + ext)
            if side.exists():
                side.rename(side.with_name(side.name + f".{_stamp()}.bak"))
        tmp.replace(db)
        flag.unlink()
        result = {"restored": name, "safety_backup": str(safety) if safety else None}
        logger.warning("Database restored from %s (safety backup: %s)", name, safety)
        return result
    except Exception as exc:  # leave the flag so the problem is visible, keep running
        logger.error("Pending restore failed: %s", exc)
        return {"error": str(exc)}


def startup() -> dict:
    """Ordered start-up hook: restore (if staged) → legacy migration."""
    res: dict = {}
    r = apply_pending_restore()
    if r:
        res["restore"] = r
    res["migration"] = migrate_legacy_data()
    return res
