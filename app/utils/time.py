"""Time utilities."""
from datetime import UTC, datetime, timezone


def utcnow() -> datetime:
    """Return current UTC time with timezone awareness."""

    return datetime.now(tz=UTC)


def parse_iso_utc(value: str) -> datetime:
    """Parse an ISO 8601 string and normalize it to UTC."""

    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


__all__ = ["utcnow", "parse_iso_utc"]
