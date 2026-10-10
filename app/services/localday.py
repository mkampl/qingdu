"""
The user's local calendar day.

Everything is stored in naive UTC, but "today" on screen means the
learner's own day: streaks, due today, reviewed today, the daily
auto-enrol batch and the weekly sparkline all roll over at local
midnight, not at UTC midnight (which is 08:00 in Shanghai).

`users.timezone` holds an IANA name, set once from the browser and
changeable in Settings. NULL (never set) and names this Python's tz
database doesn't know both fall back to UTC, which is the old behaviour.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC_ZONE = ZoneInfo("UTC")
MAX_TIMEZONE_LENGTH = 64


def utcnow() -> datetime:
    """Naive UTC, matching how timestamps are stored."""
    return datetime.utcnow()


@lru_cache(maxsize=512)
def _zone(name: str) -> ZoneInfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def is_valid_timezone(name: str | None) -> bool:
    """True for an IANA zone name the server can resolve."""
    if not name or len(name) > MAX_TIMEZONE_LENGTH:
        return False
    return _zone(name) is not None


def resolve_tz(name: str | None) -> ZoneInfo:
    """ZoneInfo for `name`; NULL or unknown names mean UTC."""
    if not name:
        return UTC_ZONE
    return _zone(name) or UTC_ZONE


def user_tz(user) -> ZoneInfo:
    return resolve_tz(getattr(user, "timezone", None))


def local_date(now: datetime, tz: ZoneInfo | None = None) -> date:
    """Calendar date in `tz` at the naive-UTC instant `now`."""
    tz = tz or UTC_ZONE
    return now.replace(tzinfo=UTC).astimezone(tz).date()


def day_start_utc(day: date, tz: ZoneInfo | None = None) -> datetime:
    """Naive-UTC instant at which local `day` begins in `tz`.

    In the rare zones whose DST switch skips midnight, the local day starts
    at the first wall-clock time that exists; zoneinfo's fold=0 lands there.
    """
    tz = tz or UTC_ZONE
    local_midnight = datetime.combine(day, time(0), tzinfo=tz)
    return local_midnight.astimezone(UTC).replace(tzinfo=None)


def start_of_today(now: datetime, tz: ZoneInfo | None = None) -> datetime:
    """Naive UTC of the local midnight that began the current local day."""
    return day_start_utc(local_date(now, tz), tz)


def end_of_local_day(now: datetime, tz: ZoneInfo | None = None, days_ahead: int = 0) -> datetime:
    """Naive UTC of the local midnight that ends the day `days_ahead` after today."""
    return day_start_utc(local_date(now, tz) + timedelta(days=days_ahead + 1), tz)


__all__ = [
    "MAX_TIMEZONE_LENGTH",
    "UTC_ZONE",
    "day_start_utc",
    "end_of_local_day",
    "is_valid_timezone",
    "local_date",
    "resolve_tz",
    "start_of_today",
    "user_tz",
    "utcnow",
]
