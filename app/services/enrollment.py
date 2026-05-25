"""
Daily auto-enrollment of HSK words into the user's 'learning' pool.

Without this the review queue dries up the moment the user finishes the
words they clicked manually. We top up to the user's `daily_new_words`
target by walking HSK levels in order (low -> high), and picking words
at random within each level. The user has to make some progress through
HSK 1 before they ever see an HSK 2 word — sequential by design.

Idempotent across a UTC day: each enrolled word logs an `auto_enroll`
UserWordEvent and we count those since midnight before adding more.
"""

from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import User, UserWord, UserWordEvent
from app.state import hsk_vocab


def _candidates_at_level(level: int, hsk_version: str) -> list[str]:
    """HSK words at exactly the given level, in the requested version's space."""
    field = "level_new" if hsk_version == "new" else "level_old"
    prefix = "new-" if hsk_version == "new" else "old-"
    out: list[str] = []
    for word, entry in hsk_vocab.items():
        raw_level = entry.get(field)
        if not raw_level or not raw_level.startswith(prefix):
            continue
        try:
            n = int(raw_level[len(prefix) :].replace("+", ""))
        except ValueError:
            continue
        if n == level:
            out.append(word)
    return out


def _max_level(hsk_version: str) -> int:
    return 9 if hsk_version == "new" else 6


def enroll_daily_words(user: User, db: Session) -> list[str]:
    """
    Enrol up to (daily_new_words - already_enrolled_today) HSK words into
    the user's 'learning' pool. Returns the list of newly enrolled words
    (possibly empty). Caller does NOT need to commit — we flush so the
    caller's next query sees the new rows, but defer commit to the caller's
    request boundary.

    Selection: walks HSK levels low -> high in the user's chosen version.
    At each level, picks at random from the words the user hasn't touched
    yet (no existing UserWord row, regardless of state — known words are
    skipped too, since "I already know it" is not a candidate for learning).
    """
    target = user.daily_new_words or 0
    if target <= 0:
        return []

    midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    already_today = (
        db.query(UserWordEvent)
        .filter(
            UserWordEvent.user_id == user.id,
            UserWordEvent.event_type == "auto_enroll",
            UserWordEvent.created_at >= midnight,
        )
        .count()
    )
    remaining = target - already_today
    if remaining <= 0:
        return []

    touched_rows = db.query(UserWord.word).filter(UserWord.user_id == user.id).all()
    touched: set[str] = {w for (w,) in touched_rows}

    version = user.hsk_focus_version or "new"
    enrolled: list[str] = []
    for level in range(1, _max_level(version) + 1):
        if remaining <= 0:
            break
        pool = [w for w in _candidates_at_level(level, version) if w not in touched]
        if not pool:
            continue
        random.shuffle(pool)
        for word in pool[:remaining]:
            db.add(UserWord(user_id=user.id, word=word, state="learning", seen_count=0))
            db.add(
                UserWordEvent(
                    user_id=user.id,
                    word=word,
                    event_type="auto_enroll",
                    new_state="learning",
                )
            )
            enrolled.append(word)
            touched.add(word)
        remaining = target - already_today - len(enrolled)

    if enrolled:
        db.flush()
    return enrolled


def enrolled_today(user: User, db: Session) -> int:
    """Number of auto-enrol events for this user since UTC midnight."""
    midnight = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(UserWordEvent)
        .filter(
            UserWordEvent.user_id == user.id,
            UserWordEvent.event_type == "auto_enroll",
            UserWordEvent.created_at >= midnight,
        )
        .count()
    )


__all__ = ["enroll_daily_words", "enrolled_today"]
