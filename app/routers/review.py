"""
SRS review queue + grading. The reading loop lives in /api/words; this
file is the *practice* loop — pull cards that are due, present them in
the selected mode, then run the grade back through FSRS to set the next
due_at.

Mode hints in the queue payload:
- recognition: just word/pinyin/meaning(s).
- dictation:   same payload, the SPA plays TTS for word.text.
- writing:     same payload, the SPA renders a hanzi-writer quiz canvas
               and grades from the stroke-mistake count.
- cloze:       reserved — needs a sample-sentence pipeline (Phase B+).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWord, UserWordEvent, get_db
from app.services import srs
from app.services.enrollment import enroll_daily_words, enrolled_today
from app.services.streak import record_activity
from app.state import hsk_vocab

router = APIRouter(tags=["Review"])


ReviewMode = Literal["recognition", "dictation", "writing", "cloze"]


class GradeRequest(BaseModel):
    word: str
    grade: int  # 1=Again, 2=Hard, 3=Good, 4=Easy
    mode: ReviewMode = "recognition"


def _enrich(word: str) -> dict:
    """
    Pull pinyin + meaning from HSK vocab for the queue payload. Words not
    in HSK (compounds + unknowns) come back with empty strings — the SPA
    will fall back to whatever it has cached from the analyze response.
    """
    entry = hsk_vocab.get(word)
    if not entry:
        return {"pinyin": "", "meaning": "", "meanings": [], "hsk_level": None}
    return {
        "pinyin": entry.get("pinyin", ""),
        "meaning": entry.get("meaning", ""),
        "meanings": entry.get("meanings", []),
        "hsk_level": entry.get("level"),
    }


@router.get("/api/review/queue")
async def review_queue(
    mode: ReviewMode = "recognition",
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    Return up to `limit` cards that are due (due_at <= now) OR have no
    due_at yet (i.e. were marked 'learning' before Phase B shipped, so
    they need a first FSRS init). Ordered by due_at ASC, NULLs first.

    Side effect (Phase #96): tops up the user's 'learning' pool with up
    to `daily_new_words` fresh HSK entries before reading the queue, so
    the queue never goes empty while there are HSK words left to learn.
    """
    enrolled = enroll_daily_words(user, db)
    if enrolled:
        db.commit()
    now = datetime.utcnow()
    rows = (
        db.query(UserWord)
        .filter(
            UserWord.user_id == user.id,
            UserWord.state == "learning",
            or_(UserWord.due_at.is_(None), UserWord.due_at <= now),
        )
        .order_by(UserWord.due_at.is_(None).desc(), UserWord.due_at.asc())
        .limit(limit)
        .all()
    )
    return {
        "mode": mode,
        "cards": [
            {
                "word": r.word,
                "due_at": r.due_at.isoformat() if r.due_at else None,
                "stability": r.stability,
                "difficulty": r.difficulty,
                **_enrich(r.word),
            }
            for r in rows
        ],
    }


@router.post("/api/review/grade")
async def grade_card(
    payload: GradeRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    if payload.grade not in srs.VALID_GRADES:
        raise HTTPException(status_code=400, detail=f"grade must be one of {srs.VALID_GRADES}")

    row = (
        db.query(UserWord)
        .filter(UserWord.user_id == user.id, UserWord.word == payload.word)
        .first()
    )
    if row is None:
        # Auto-promote: grading a word we've never seen creates the row.
        row = UserWord(user_id=user.id, word=payload.word, state="learning", seen_count=1)
        db.add(row)

    updated = srs.apply_grade(row.fsrs_state, payload.grade)
    row.fsrs_state = updated["fsrs_state"]
    row.stability = updated["stability"]
    row.difficulty = updated["difficulty"]
    row.due_at = updated["due_at"]
    row.last_reviewed_at = updated["last_reviewed_at"]
    row.updated_at = datetime.utcnow()

    db.add(
        UserWordEvent(
            user_id=user.id,
            word=payload.word,
            event_type="review",
            new_state=row.state,
            grade=payload.grade,
        )
    )
    record_activity(user, db)
    db.commit()
    return {
        "word": payload.word,
        "due_at": row.due_at.isoformat() if row.due_at else None,
        "stability": row.stability,
        "difficulty": row.difficulty,
    }


@router.get("/api/review/stats")
async def review_stats(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    Summary for the nav badge + ReviewView dashboard.
    - `due_now`: cards currently due (queue depth right now).
    - `due_today`: cards that will be due before tomorrow midnight UTC.
    - `learning`: total cards in the 'learning' state.
    - `reviewed_today`: reviews logged since UTC midnight.
    """
    now = datetime.utcnow()
    midnight_tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    due_now = (
        db.query(UserWord)
        .filter(
            UserWord.user_id == user.id,
            UserWord.state == "learning",
            or_(UserWord.due_at.is_(None), UserWord.due_at <= now),
        )
        .count()
    )
    due_today = (
        db.query(UserWord)
        .filter(
            UserWord.user_id == user.id,
            UserWord.state == "learning",
            or_(
                UserWord.due_at.is_(None),
                UserWord.due_at < midnight_tomorrow,
            ),
        )
        .count()
    )
    learning = (
        db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.state == "learning").count()
    )
    reviewed_today = (
        db.query(UserWordEvent)
        .filter(
            UserWordEvent.user_id == user.id,
            UserWordEvent.event_type == "review",
            UserWordEvent.created_at >= midnight_today,
        )
        .count()
    )
    return {
        "due_now": due_now,
        "due_today": due_today,
        "learning": learning,
        "reviewed_today": reviewed_today,
        # Phase #96 — counters for the "new today: X / Y" badge.
        "new_today": enrolled_today(user, db),
        "daily_target": user.daily_new_words or 0,
    }
