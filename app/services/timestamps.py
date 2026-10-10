"""
Timestamps on the wire.

The schema stores naive UTC datetimes (`datetime.utcnow()` everywhere).
`naive.isoformat()` has no offset, and browsers parse an offset-less
date-time string as *local* time — so west of UTC a card due "in one
minute" looked hours away, and east of UTC everything looked overdue.
Every datetime the API returns goes through `iso_utc()`, which always
carries an explicit `Z`.
"""

from __future__ import annotations

from datetime import UTC, datetime


def iso_utc(dt: datetime | None) -> str | None:
    """ISO 8601 string with a trailing `Z`; naive input is taken as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat() + "Z"
