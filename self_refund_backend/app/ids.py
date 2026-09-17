"""Identifier helpers."""
import uuid


def parse_uuid(value):
    """Return a UUID, or None if ``value`` is not a valid UUID."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None
