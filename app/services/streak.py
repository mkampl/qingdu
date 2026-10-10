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

Streak freezes (Phase F3): earned automatically every FREEZE_MILESTONE_DAYS
of streak, banked up to MAX_STREAK_FREEZES. There's no purchase path — this
app has no payment rails, and an earned-only freeze fits the low-pressure
tone better anyway. A freeze covers exactly one missed day each; missing N
consecutive days consumes N banked freezes to bridge the gap, and the
streak only actually breaks once the gap is longer than what's banked.
There's no background job, so "did a freeze bridge this gap" is computed
lazily in both directions: `record_activity` spends freezes (and awards new
ones) when the user next acts, and `current_streak` mirrors the same gap
math read-only so the displayed count stays consistent in between.

Days are the user's local calendar days (services.localday). Rows written
before `users.timezone` existed hold UTC dates; `rebase_for_timezone`
moves `streak_last_active` onto the new zone's calendar whenever the
timezone setting changes, so switching zones never costs a streak:

- the date moves by the difference between "today" in the new zone and
  "today" in the old zone, when that difference is positive (switching
  east, e.g. UTC -> Asia/Shanghai after 16:00 UTC: yesterday-UTC becomes
  yesterday-local and today-UTC becomes today-local);
- switching west it is only clamped to the new local today, never pulled
  back, so the learner gets the longer of the two windows to continue.

`record_activity` and `current_streak` also treat a last-active date that
lies in the local future (left over from a zone switch) as "today".
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.database import User
from app.services import localday

logger = logging.getLogger(__name__)

MAX_STREAK_FREEZES = 2
FREEZE_MILESTONE_DAYS = 7


def _gap_days(last: date, today: date) -> int:
    """Number of full days with no activity between `last` and `today`.

    0 means today or yesterday (a normal continuation, no day skipped).
    """
    return (today - last).days - 1


def record_activity(user: User, db: Session, now: datetime | None = None) -> None:
    """
    Update the user's streak counters based on the user's local date. Callers
    don't need to commit — they're already in the middle of a writing
    request and a commit follows. We do flush so the values are visible
    in subsequent queries within the same transaction.

    The `user` argument is often a detached object (loaded inside a
    different session that's already closed — that's how get_current_user
    is wired). Merge it into the caller's session so the column writes
    actually land.
    """
    user = db.merge(user)
    today = localday.local_date(now or localday.utcnow(), localday.user_tz(user))
    last = user.streak_last_active
    freezes = user.streak_freeze_count or 0

    if last is not None and last >= today:
        return  # already counted today (or a zone switch put it ahead)

    gap = _gap_days(last, today) if last is not None else None

    if gap is not None and 0 <= gap <= freezes:
        # Continues either directly (gap 0) or bridged by banked freezes.
        user.streak_freeze_count = freezes - gap
        user.streak_count = (user.streak_count or 0) + 1
    else:
        # Either first ever activity, or the gap outran the banked freezes.
        user.streak_count = 1

    if (user.streak_count or 0) % FREEZE_MILESTONE_DAYS == 0:
        user.streak_freeze_count = min(MAX_STREAK_FREEZES, (user.streak_freeze_count or 0) + 1)

    user.streak_last_active = today
    db.flush()


def current_streak(user: User, today: date | None = None, now: datetime | None = None) -> int:
    """
    Return the streak count as the user would see it *right now*. If the
    gap since `streak_last_active` is longer than what's banked in
    freezes, the persisted count is stale (we only refresh it on next
    activity), so we treat it as 0.
    """
    if today is None:
        today = localday.local_date(now or localday.utcnow(), localday.user_tz(user))
    if user.streak_last_active is None:
        return 0
    gap = max(0, _gap_days(user.streak_last_active, today))
    if gap > (user.streak_freeze_count or 0):
        return 0
    return user.streak_count or 0


def rebase_for_timezone(
    user: User,
    old_tz: ZoneInfo | None,
    new_tz: ZoneInfo | None,
    now: datetime | None = None,
) -> None:
    """Move `streak_last_active` onto the new zone's calendar (see module doc).

    `user` must already be attached to the caller's session; the caller
    commits. No-op when the user has no streak date or the zones agree on
    today's date.
    """
    last = user.streak_last_active
    if last is None:
        return
    now = now or localday.utcnow()
    old_today = localday.local_date(now, old_tz)
    new_today = localday.local_date(now, new_tz)
    shift = new_today - old_today
    rebased = last + shift if shift.days > 0 else last
    rebased = min(rebased, new_today)
    if rebased != last:
        logger.info("streak: user %s timezone switch, last_active %s -> %s", user.id, last, rebased)
        user.streak_last_active = rebased


__all__ = [
    "current_streak",
    "rebase_for_timezone",
    "record_activity",
    "MAX_STREAK_FREEZES",
    "FREEZE_MILESTONE_DAYS",
]
