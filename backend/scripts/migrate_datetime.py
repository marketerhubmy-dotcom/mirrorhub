"""
Legacy datetime normalization script.

Finds naive UTC timestamps (stored without +00:00 or Z suffix) in the SQLite
database and appends +00:00 to make them timezone-aware UTC strings.

Usage:
    python scripts/migrate_datetime.py [--db PATH] [--dry-run]

Safety:
  - Creates a timestamped backup of the database before modifying it.
  - Idempotent: rows that already have +00:00 or Z are left untouched.
  - Prints a per-table summary of rows normalised.
  - Use --dry-run to preview changes without writing.
"""
import argparse
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# ── Regex: matches ISO datetime strings WITHOUT timezone marker ───────────────
# e.g. "2024-01-15T09:30:00" or "2024-01-15 09:30:00.123456"
# Does NOT match strings already ending in +00:00, Z, or +HH:MM
_NAIVE_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?$"
)

# ── Tables and datetime columns to check ─────────────────────────────────────
# Extend this list if new tables are added.
DATETIME_COLUMNS: dict[str, list[str]] = {
    "campaigns": [
        "created_at", "updated_at", "started_at", "finished_at", "scheduled_at"
    ],
    "campaign_jobs": [
        "created_at", "updated_at", "started_at", "finished_at"
    ],
    "agent_goals": [
        "created_at", "updated_at"
    ],
    "agent_memory": [
        "recorded_at"
    ],
    "execution_jobs": [
        "created_at", "updated_at", "started_at", "completed_at"
    ],
    "device_profiles": [
        "created_at", "updated_at", "last_health_check"
    ],
    "workflow_sessions": [
        "started_at", "finished_at"
    ],
    "workflow_events": [
        "recorded_at"
    ],
    "screen_analyses": [
        "captured_at", "analysed_at"
    ],
}


def _backup(db_path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = db_path.parent / f"{db_path.stem}_backup_{ts}.db"
    shutil.copy2(db_path, backup)
    print(f"[backup] {backup}")
    return backup


def _normalize(conn: sqlite3.Connection, table: str, columns: list[str],
               dry_run: bool) -> int:
    """Normalise naive timestamps in *table*. Returns count of rows updated."""
    cur = conn.cursor()

    # Fetch all rows for the target columns
    col_list = ", ".join(["rowid"] + columns)

    try:
        cur.execute(f"SELECT {col_list} FROM {table}")  # noqa: S608
    except sqlite3.OperationalError as exc:
        # Table or column might not exist in older schema versions
        print(f"  [skip] {table}: {exc}")
        return 0

    rows = cur.fetchall()
    updated = 0

    for row in rows:
        rowid = row[0]
        changes: dict[str, str] = {}

        for idx, col in enumerate(columns):
            val = row[1 + idx]
            if val is None:
                continue
            if isinstance(val, str) and _NAIVE_ISO.match(val):
                changes[col] = val + "+00:00"

        if not changes:
            continue

        if not dry_run:
            set_clause = ", ".join(f"{c} = ?" for c in changes)
            cur.execute(
                f"UPDATE {table} SET {set_clause} WHERE rowid = ?",  # noqa: S608
                [*changes.values(), rowid],
            )
        updated += 1

    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize naive UTC datetimes in mirrorhub.db")
    parser.add_argument(
        "--db",
        default=str(Path(__file__).parent.parent / "mirrorhub.db"),
        help="Path to the SQLite database file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[error] Database not found: {db_path}")
        raise SystemExit(1)

    if not args.dry_run:
        _backup(db_path)

    conn = sqlite3.connect(str(db_path))
    total = 0

    try:
        conn.execute("PRAGMA foreign_keys=ON")
        for table, columns in DATETIME_COLUMNS.items():
            count = _normalize(conn, table, columns, dry_run=args.dry_run)
            if count:
                tag = "[dry-run]" if args.dry_run else "[update]"
                print(f"  {tag} {table}: {count} row(s) normalised")
                total += count

        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    if total == 0:
        print("[ok] No naive timestamps found — database is already normalised.")
    else:
        action = "would update" if args.dry_run else "updated"
        print(f"\n[done] {action} {total} row(s) across {len(DATETIME_COLUMNS)} tables.")


if __name__ == "__main__":
    main()
