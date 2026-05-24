"""
Daily-activity streak tracking. Any "this user engaged today" event hits
`record_activity` — the function is idempotent within a single day and
collapses every qualifying interaction into one streak bump.

What counts as a qualifying activity:
- Marking a word's state (POST /api/words/state, bulk-mark-known)
- Grading a review card (POST /api/review/grade)

Reading time without marking words doesn't count for now — it's hard to
measure honestly without a tab-focus heartbeat, and adding one would
amplify the privacy footprint of the app. We can revisit if the streak
turns out to be too easy to drop.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.database import User


def record_activity(user: User, db: Session) -> None:
    """
    Update the user's streak counters based on today's UTC date. Callers
    don't need to commit — they're already in the middle of a writing
    request and a commit follows. We do flush so the values are visible
    in subsequent queries within the same transaction.

    The `user` argument is often a detached object (loaded inside a
    different session that's already closed — that's how get_current_user
    is wired). Merge it into the caller's session so the column writes
    actually land.
    """
    today = datetime.utcnow().date()
    user = db.merge(user)
    last = user.streak_last_active

    if last == today:
        return  # already counted today

    if last == today - timedelta(days=1):
        user.streak_count = (user.streak_count or 0) + 1
    else:
        # Either first ever activity, or the previous streak lapsed.
        user.streak_count = 1

    user.streak_last_active = today
    db.flush()


def current_streak(user: User, today: date | None = None) -> int:
    """
    Return the streak count as the user would see it *right now*. If
    `streak_last_active` is older than yesterday the persisted count is
    stale (we only refresh it on next activity), so we treat it as 0.
    """
    if today is None:
        today = datetime.utcnow().date()
    if user.streak_last_active is None:
        return 0
    if user.streak_last_active < today - timedelta(days=1):
        return 0
    return user.streak_count or 0


__all__ = ["current_streak", "record_activity"]
