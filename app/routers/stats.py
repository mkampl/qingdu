"""
Activity stats for the user dashboard. Right now just a 7-day rollup
that powers the sparkline on /review; will grow as Phase F surfaces
more per-user analytics.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWordEvent, get_db

router = APIRouter(tags=["Stats"])

# Event types that record a word turning 'known'.
KNOWN_EVENT_TYPES = ("state_change", "bulk_mark_known")


@router.get("/api/stats/weekly")
async def weekly_activity(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    Return a 7-element array of {date, reviews, marked_known} — oldest day
    first, newest day last (today). Days with no activity are still in the
    array with zero counts so the chart can plot a continuous baseline.
    """
    today = datetime.utcnow().date()
    start = today - timedelta(days=6)
    start_dt = datetime.combine(start, datetime.min.time())

    # Two aggregates in two queries — simpler than juggling the WHERE
    # branches in one. Both are cheap on the indexed events table.
    review_rows = (
        db.query(func.date(UserWordEvent.created_at), func.count())
        .filter(
            UserWordEvent.user_id == user.id,
            UserWordEvent.event_type == "review",
            UserWordEvent.created_at >= start_dt,
        )
        .group_by(func.date(UserWordEvent.created_at))
        .all()
    )
    # Words that became known: explicit marks (state_change), bulk marks,
    # and FSRS promotions in grade_card (also a state_change). Review
    # events carry new_state too and must not count. The HSK import logs
    # one row for many words, so sum word_count (NULL = one word).
    known_rows = (
        db.query(
            func.date(UserWordEvent.created_at),
            func.sum(func.coalesce(UserWordEvent.word_count, 1)),
        )
        .filter(
            UserWordEvent.user_id == user.id,
            UserWordEvent.new_state == "known",
            UserWordEvent.event_type.in_(KNOWN_EVENT_TYPES),
            UserWordEvent.created_at >= start_dt,
        )
        .group_by(func.date(UserWordEvent.created_at))
        .all()
    )
    reviews_by_day = {_normalize_day(d): c for d, c in review_rows}
    known_by_day = {_normalize_day(d): c for d, c in known_rows}

    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        days.append(
            {
                "date": key,
                "reviews": reviews_by_day.get(key, 0),
                "marked_known": int(known_by_day.get(key, 0) or 0),
            }
        )
    return {"days": days}


def _normalize_day(value) -> str:
    """SQLAlchemy's date() returns either a string or a date depending on
    the dialect. Force ISO YYYY-MM-DD either way."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
