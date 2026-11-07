"""Baseline — snapshot of schema at Release 2.1.1.

This revision captures the current table structure as the starting point
for all future Alembic-managed migrations. It uses create_all(checkfirst=True)
so running against an existing database is safe and idempotent.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Ensure all tables exist.

    create_all(checkfirst=True) is idempotent — safe to run against a DB
    that already has some or all of the tables. New installations get
    everything; existing installations skip tables that already exist.
    """
    from sqlalchemy import inspect

    bind = op.get_bind()

    # Import models to populate metadata
    from app.models.database import Base
    import app.campaign.models         # noqa: F401
    import app.agents.models           # noqa: F401
    import app.execution.models        # noqa: F401
    import app.orchestrator.models     # noqa: F401
    import app.workflows.models        # noqa: F401

    Base.metadata.create_all(bind=bind, checkfirst=True)

    # Enable FK enforcement for every new connection
    bind.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    """
    Baseline cannot be downgraded — it represents the initial schema state.

    If you need a blank database, delete mirrorhub.db and restart the app.
    """
    raise NotImplementedError(
        "Downgrade from baseline is not supported. "
        "Delete mirrorhub.db to start fresh."
    )
