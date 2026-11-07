"""
Standalone safe DB migration script.

Usage (from project root):
    python backend/scripts/safe_migrate.py
    python backend/scripts/safe_migrate.py --dry-run

What it does:
  1. Checks whether mirrorhub.db exists.
  2. Reads PRAGMA table_info for each managed table.
  3. If any required column is missing:
       a. Creates a timestamped backup of mirrorhub.db.
       b. Adds each missing column via ALTER TABLE.
       c. Logs a summary.

Safe to run multiple times (idempotent).

This script mirrors app/migration.py but runs synchronously so it
can be invoked from the command line or from validate.bat without
starting the full FastAPI app.
"""
import argparse
import io
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows consoles that default to cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent.parent
DB_PATH = ROOT / "backend" / "mirrorhub.db"

REQUIRED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "content_jobs": [
        ("tiktok_product_name", "TEXT DEFAULT ''"),
        ("publish_mode",        "VARCHAR(16) DEFAULT 'manual'"),
    ],
}


def detect_missing(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    missing = []
    cur = conn.cursor()
    for table, columns in REQUIRED_COLUMNS.items():
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not cur.fetchone():
            print(f"  [SKIP] Table '{table}' does not exist yet — will be created by init_db()")
            continue
        cur.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cur.fetchall()}
        for col_name, col_def in columns:
            if col_name not in existing:
                missing.append((table, col_name, col_def))
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description="MirrorHub safe DB migration")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying the DB")
    args = parser.parse_args()

    print(f"DB path: {DB_PATH}")

    if not DB_PATH.exists():
        print("mirrorhub.db not found — nothing to migrate. "
              "Start the app once to create the DB.")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    try:
        missing = detect_missing(conn)
    finally:
        conn.close()

    if not missing:
        print("✅ Schema is up to date — no migration needed.")
        return 0

    print(f"\nMissing columns ({len(missing)}):")
    for table, col, defn in missing:
        print(f"  {table}.{col}  [{defn}]")

    if args.dry_run:
        print("\n(dry-run) No changes made.")
        return 0

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.parent / f"mirrorhub_backup_{ts}.db"
    shutil.copy2(str(DB_PATH), str(backup))
    print(f"\n📦 Backup created: {backup}")

    # Apply
    conn = sqlite3.connect(str(DB_PATH))
    try:
        for table, col, defn in missing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
            print(f"✅ Added: {table}.{col}")
        conn.commit()
    finally:
        conn.close()

    print("\nMigration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
