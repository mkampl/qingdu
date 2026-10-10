"""
One definition of "due" for every screen that counts or lists due cards.

The Review page (`/api/review/stats`, `/api/review/queue`) and the `/words`
due chips used to compute their own cutoffs, so the nav badge could say
"38 due today" while `/words` → Due today listed fewer. Both now go through
`end_of_day()` and `due_clause()`.

Rules:
- Only rows in ACTIVE_REVIEW_STATES can be due. Ignored words never are.
- A row with no `due_at` is a card that has never been scheduled (freshly
  clicked or auto-enrolled). The review queue serves those first, so they
  count as due under every cutoff.
- Day boundaries are the user's local midnight (services.localday);
  without a stored timezone that is UTC midnight.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.database import UserWord
from app.services import localday

# State values that participate in the review queue. 'known' joined
# 'learning' once it became a high-stability SRS card instead of a
# terminal opt-out; only 'ignored' (and absence of row) stay out of
# the rotation.
ACTIVE_REVIEW_STATES = ("learning", "known")


def utcnow() -> datetime:
    """Naive UTC, matching how due_at is stored."""
    return localday.utcnow()


def end_of_day(now: datetime, days_ahead: int = 0, tz: ZoneInfo | None = None) -> datetime:
    """Local midnight (as naive UTC) that ends the day `days_ahead` days after `now`.

    days_ahead=0 is "end of today" (the Review page's due_today), 1 is the
    end of tomorrow, 7 the end of the day a week from now. `tz` is the
    user's zone (localday.user_tz); None means UTC.
    """
    return localday.end_of_local_day(now, tz, days_ahead)


def due_clause(cutoff: datetime) -> ColumnElement[bool]:
    """Rows that are due strictly before `cutoff` (or were never scheduled)."""
    return and_(
        UserWord.state.in_(ACTIVE_REVIEW_STATES),
        or_(UserWord.due_at.is_(None), UserWord.due_at < cutoff),
    )


# user.review_window values. "today"/"tomorrow" look ahead to the end of
# that local day so a once-a-day session covers everything coming due;
# "now" is the strict FSRS pull (due_at <= now).
REVIEW_WINDOWS = ("now", "today", "tomorrow")
DEFAULT_REVIEW_WINDOW = "today"


def review_window_clause(
    window: str | None, now: datetime, tz: ZoneInfo | None = None
) -> ColumnElement[bool]:
    """Rows the review queue serves under `window`.

    The single definition behind both `/api/review/queue` and the
    `due_in_window` count in `/api/review/stats`, so the nav badge and the
    Start button can never disagree with what a session actually opens.
    """
    window = window or DEFAULT_REVIEW_WINDOW
    if window == "today":
        return due_clause(end_of_day(now, 0, tz))
    if window == "tomorrow":
        return due_clause(end_of_day(now, 1, tz))
    return and_(
        UserWord.state.in_(ACTIVE_REVIEW_STATES),
        or_(UserWord.due_at.is_(None), UserWord.due_at <= now),
    )
