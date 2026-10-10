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
- Day boundaries are UTC midnight (see L22 for the local-day follow-up).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.database import UserWord

# State values that participate in the review queue. 'known' joined
# 'learning' once it became a high-stability SRS card instead of a
# terminal opt-out; only 'ignored' (and absence of row) stay out of
# the rotation.
ACTIVE_REVIEW_STATES = ("learning", "known")


def utcnow() -> datetime:
    """Naive UTC, matching how due_at is stored."""
    return datetime.utcnow()


def end_of_day(now: datetime, days_ahead: int = 0) -> datetime:
    """UTC midnight that ends the day `days_ahead` days after `now`.

    days_ahead=0 is "end of today" (the Review page's due_today), 1 is the
    end of tomorrow, 7 the end of the day a week from now.
    """
    return (now + timedelta(days=days_ahead + 1)).replace(hour=0, minute=0, second=0, microsecond=0)


def due_clause(cutoff: datetime) -> ColumnElement[bool]:
    """Rows that are due strictly before `cutoff` (or were never scheduled)."""
    return and_(
        UserWord.state.in_(ACTIVE_REVIEW_STATES),
        or_(UserWord.due_at.is_(None), UserWord.due_at < cutoff),
    )
