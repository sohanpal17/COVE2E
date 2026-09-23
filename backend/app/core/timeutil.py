from datetime import datetime, timezone
from typing import Optional


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite drops tzinfo; normalise to UTC-aware for arithmetic."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def now() -> datetime:
    return datetime.now(timezone.utc)
