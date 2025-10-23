"""Time utilities."""
from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return current UTC time with timezone awareness."""

    return datetime.now(tz=UTC)
