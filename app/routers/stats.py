"""Activity stats: the 7-day rollup behind the sparkline on /review."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWordEvent, get_db
from app.services import localday
from app.services.localday import day_start_utc, local_date, user_tz

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

    Days are the user's local calendar days (users.timezone). SQLite's
    date() only knows UTC and DST makes the offset vary within a week, so
    the week's events are bucketed here instead of in SQL.
    """
    tz = user_tz(user)
    today = local_date(localday.utcnow(), tz)
    start = today - timedelta(days=6)
    start_dt = day_start_utc(start, tz)

    # Reviews, plus words that became known: explicit marks (state_change),
    # bulk marks, and FSRS promotions in grade_card (also a state_change).
    # Review events carry new_state too and must not count as known. The
    # HSK import logs one row for many words, so sum word_count (NULL = one
    # word).
    rows = (
        db.query(
            UserWordEvent.created_at,
            UserWordEvent.event_type,
            UserWordEvent.new_state,
            func.coalesce(UserWordEvent.word_count, 1),
        )
        .filter(
            UserWordEvent.user_id == user.id,
            UserWordEvent.created_at >= start_dt,
            or_(
                UserWordEvent.event_type == "review",
                (UserWordEvent.new_state == "known")
                & UserWordEvent.event_type.in_(KNOWN_EVENT_TYPES),
            ),
        )
        .all()
    )
    reviews_by_day: Counter[str] = Counter()
    known_by_day: Counter[str] = Counter()
    for created_at, event_type, new_state, word_count in rows:
        key = local_date(created_at, tz).isoformat()
        if event_type == "review":
            reviews_by_day[key] += 1
        elif new_state == "known":
            known_by_day[key] += int(word_count or 1)

    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        days.append(
            {
                "date": key,
                "reviews": reviews_by_day.get(key, 0),
                "marked_known": known_by_day.get(key, 0),
            }
        )
    return {"days": days}
