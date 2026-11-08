"""Custom SQLAlchemy column types."""
from datetime import datetime, timezone

from sqlalchemy.types import DateTime, TypeDecorator


class UTCDateTime(TypeDecorator):
    """
    Always timezone-aware UTC in Python, naive-UTC in SQLite.

    SQLite has no tz support, so SQLAlchemy hands back naive datetimes, which
    raise TypeError when compared with ``datetime.now(timezone.utc)``.
    """
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
