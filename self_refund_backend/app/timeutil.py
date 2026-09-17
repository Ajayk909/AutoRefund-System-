"""UTC helpers. Database columns store naive UTC datetimes."""
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
