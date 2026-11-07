"""
Alembic migration environment.

Uses a synchronous SQLite URL (stripped of +aiosqlite) so that Alembic's
standard run_migrations_online() works without async scaffolding.
Imports every SQLAlchemy model so autogenerate can diff the schema.
"""
import re
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Add backend/ to sys.path so `from app...` imports work ───────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Load all models so metadata is populated ─────────────────────────────────
from app.models.database import Base          # noqa: F401
import app.campaign.models                    # noqa: F401
import app.agents.models                      # noqa: F401
import app.execution.models                   # noqa: F401
import app.orchestrator.models                # noqa: F401
import app.workflows.models                   # noqa: F401
import app.vision.models                      # noqa: F401

target_metadata = Base.metadata

# ── Alembic config ────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Strip async driver prefix so Alembic can use a sync engine
raw_url: str = config.get_main_option("sqlalchemy.url", "")
sync_url = re.sub(r"\+aiosqlite", "", raw_url)


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = sync_url

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        connection.execute(
            connection.dialect.text("PRAGMA foreign_keys=ON")
            if hasattr(connection.dialect, "text")
            else __import__("sqlalchemy").text("PRAGMA foreign_keys=ON")
        )
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,    # required for SQLite ALTER TABLE emulation
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
