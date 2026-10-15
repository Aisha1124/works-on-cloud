"""Shop time. Everything the owner or buyer sees is in Singapore time.

Singapore has no daylight saving, so a fixed +08:00 offset is exact and needs no tz database
(Windows has none without the tzdata package).
"""

from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8), "Asia/Singapore")


def now_sg() -> datetime:
    return datetime.now(SGT)


def to_sg(dt: datetime) -> datetime:
    """Naive datetimes are read as Singapore time; aware ones are converted."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=SGT)
    return dt.astimezone(SGT)
