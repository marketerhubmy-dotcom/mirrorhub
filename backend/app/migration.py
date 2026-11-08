"""
Safe startup migration for SQLite.

Adds missing columns to existing tables without dropping data.
Called once at app startup (before init_db) via main.py lifespan.

Strategy:
  1. Read PRAGMA table_info for each table.
  2. Compare against REQUIRED_COLUMNS.
  3. If any column is missing, back up mirrorhub.db first.
  4. Issue ALTER TABLE ... ADD COLUMN for each missing column.
  5. Log the backup path so the operator can recover if needed.

This is intentionally minimal — no Alembic, no migration chain.
It only adds columns; it never drops, renames, or changes types.
"""
import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolved once at import time — same root as database.py
from app.core import runtime_paths

DB_PATH = runtime_paths.db_path()

# table_name -> list of (column_name, column_definition)
REQUIRED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "devices": [
        ("hw_serial",        "VARCHAR(64)"),
        ("model",            "VARCHAR(64) DEFAULT ''"),
        ("manufacturer",     "VARCHAR(64) DEFAULT ''"),
        ("android_version",  "VARCHAR(16) DEFAULT ''"),
        ("sdk",              "INTEGER DEFAULT 0"),
        ("transport",        "VARCHAR(16) DEFAULT ''"),
        ("state",            "VARCHAR(24) DEFAULT 'absent'"),
        ("storage_total_mb", "INTEGER DEFAULT 0"),
        ("storage_free_mb",  "INTEGER DEFAULT 0"),
        ("screen_w",         "INTEGER DEFAULT 0"),
        ("screen_h",         "INTEGER DEFAULT 0"),
        ("tags",             "TEXT DEFAULT '[]'"),
        ("group_name",       "VARCHAR(64) DEFAULT ''"),
        ("notes",            "TEXT DEFAULT ''"),
        ("last_error",       "TEXT DEFAULT ''"),
    ],
    "content_jobs": [
        ("tiktok_product_name",      "TEXT DEFAULT ''"),
        ("publish_mode",             "VARCHAR(16) DEFAULT 'manual'"),
        ("selected_product_id",      "INTEGER"),
        ("product_snapshot",         "TEXT"),
        # MVP 0.6 — added without requiring DB deletion
        ("avatar",                   "TEXT DEFAULT ''"),
        ("cover_hook",               "TEXT DEFAULT ''"),
        ("custom_instructions",      "TEXT DEFAULT ''"),
        ("video_type",               "TEXT DEFAULT ''"),
        ("selected_content_angle",   "TEXT DEFAULT ''"),
    ],
    "saved_products": [
        ("platform",                  "VARCHAR(32) DEFAULT 'tiktok_shop'"),
        ("product_id",                "VARCHAR(256)"),
        ("shop_name",                 "TEXT DEFAULT ''"),
        ("reference_image_path",      "VARCHAR(512)"),
        ("key_benefits",              "TEXT DEFAULT '[]'"),
        ("common_pain_points",        "TEXT DEFAULT '[]'"),
        ("buying_motivations",        "TEXT DEFAULT '[]'"),
        ("suggested_content_angles",  "TEXT DEFAULT '[]'"),
        ("target_audience",           "TEXT DEFAULT ''"),
        ("default_video_objective",   "TEXT DEFAULT ''"),
        ("default_video_style",       "TEXT DEFAULT ''"),
        ("tiktok_product_name",       "TEXT DEFAULT ''"),
        ("updated_at",                "DATETIME"),
        ("target_audience_options",   "TEXT DEFAULT '[]'"),
        ("source_type",               "VARCHAR(32) DEFAULT 'url'"),
    ],
}


async def safe_migrate_db() -> None:
    """Detect and add missing columns; back up DB before any schema change."""
    if not DB_PATH.exists():
        logger.debug("mirrorhub.db not found — will be created fresh by init_db()")
        return

    import aiosqlite  # only imported when db file actually exists

    # ── Pass 1: determine what's missing ────────────────────────────────────
    missing: list[tuple[str, str, str]] = []  # (table, col_name, col_def)

    async with aiosqlite.connect(str(DB_PATH)) as conn:
        for table, columns in REQUIRED_COLUMNS.items():
            # Check whether the table exists at all
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if not await cur.fetchone():
                continue  # table will be created by init_db()

            cur = await conn.execute(f"PRAGMA table_info({table})")
            existing = {row[1] async for row in cur}

            for col_name, col_def in columns:
                if col_name not in existing:
                    missing.append((table, col_name, col_def))

    if not missing:
        logger.debug("DB schema up to date — no migration needed")
        return

    # ── Back up before touching the file ────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = runtime_paths.backups_dir() / f"mirrorhub_{ts}_pre-schema-change.db"
    shutil.copy2(str(DB_PATH), str(backup_path))
    logger.info("📦 DB backup before migration: %s", backup_path)

    # ── Pass 2: apply ALTER TABLE statements ─────────────────────────────────
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        for table, col_name, col_def in missing:
            await conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
            )
            logger.info("✅ Added column: %s.%s (%s)", table, col_name, col_def)
        await conn.commit()

    logger.info(
        "Migration complete — %d column(s) added. "
        "Backup at: %s",
        len(missing),
        backup_path,
    )


async def safe_create_indexes() -> None:
    """Create performance indexes. Uses IF NOT EXISTS — safe to re-run on every startup."""
    if not DB_PATH.exists():
        return

    import aiosqlite

    _INDEXES = [
        "CREATE INDEX IF NOT EXISTS idx_saved_products_url ON saved_products(url)",
        "CREATE INDEX IF NOT EXISTS idx_saved_products_product_id ON saved_products(product_id)",
    ]

    async with aiosqlite.connect(str(DB_PATH)) as conn:
        for stmt in _INDEXES:
            await conn.execute(stmt)
        await conn.commit()

    logger.debug("DB indexes verified")
