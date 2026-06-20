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
from app.services import cloze, srs
from app.services.enrollment import enroll_daily_words, enrolled_today
from app.services.script import to_user_script
from app.services.streak import record_activity
from app.services.word_info import lookup_pinyin_meaning
from app.state import cedict_vocab, hsk_vocab

router = APIRouter(tags=["Review"])

# State values that participate in the review queue. 'known' joined
# 'learning' once it became a high-stability SRS card instead of a
# terminal opt-out; only 'ignored' (and absence of row) stay out of
# the rotation. Auto-transitions in grade_card move rows between
# 'learning' and 'known' based on the FSRS stability after grading.
ACTIVE_REVIEW_STATES = ("learning", "known")
KNOWN_STABILITY_THRESHOLD_DAYS = 90.0


ReviewMode = Literal["recognition", "dictation", "writing", "cloze"]


class GradeRequest(BaseModel):
    word: str
    grade: int  # 1=Again, 2=Hard, 3=Good, 4=Easy
    mode: ReviewMode = "recognition"


def _enrich(row: UserWord) -> dict:
    """
    Pinyin + meaning for the queue payload. Prefer the snapshot stored on
    the UserWord row (Phase #96 — survives unknown-word-cache TTLs and
    package re-imports); fall back to the live HSK entry for HSK words
    that pre-date the snapshot columns. The lazy backfill in the queue
    handler writes the values back to the row after this call.
    """
    pinyin = row.pinyin or ""
    meaning = row.meaning or ""
    entry = hsk_vocab.get(row.word)
    cedict_entry = cedict_vocab.get(row.word)
    # Prefer the meanings list from the richer source: HSK entries already
    # have CC-CEDICT meanings overlaid at startup, so hsk_vocab is the
    # primary; cedict_vocab covers non-HSK literary/proper-noun terms.
    meanings = (entry or cedict_entry or {}).get("meanings", []) or []
    hsk_level = entry.get("level") if entry else None

    if not pinyin or not meaning:
        looked_up_pinyin, looked_up_meaning = lookup_pinyin_meaning(row.word)
        if not pinyin:
            pinyin = looked_up_pinyin
        if not meaning:
            meaning = looked_up_meaning

    if not meanings and meaning:
        meanings = [meaning]

    # Phase #120 — tagged glosses. Each is one (source, source_tag,
    # meaning, pinyin) row, surfaced in creation order so the
    # dictionary entry (which we always seed first) lands at index 0
    # and package entries follow. The frontend renders these with
    # provenance chips ("[Dao De Jing]").
    glosses_payload = [
        {
            "source": g.source,
            "tag": g.source_tag,
            "meaning": g.meaning,
            "pinyin": g.pinyin,
        }
        for g in (row.glosses or [])
    ]

    return {
        "pinyin": pinyin,
        "meaning": meaning,
        "meanings": meanings,
        "hsk_level": hsk_level,
        "glosses": glosses_payload,
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
    # Phase #119 — look-ahead window. People review once a day, not every
    # 30 minutes; widening the cutoff to "today" covers the typical session
    # without forcing the user to wait for each card to flip due. Strict
    # FSRS-conformant pull is still available via review_window='now'.
    window = user.review_window or "today"
    if window == "today":
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = midnight
    elif window == "tomorrow":
        midnight = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = midnight
    else:
        cutoff = now
    rows = (
        db.query(UserWord)
        .filter(
            UserWord.user_id == user.id,
            UserWord.state.in_(ACTIVE_REVIEW_STATES),
            or_(UserWord.due_at.is_(None), UserWord.due_at <= cutoff),
        )
        .order_by(UserWord.due_at.is_(None).desc(), UserWord.due_at.asc())
        .limit(limit)
        .all()
    )
    # Build payload and lazy-backfill the snapshot columns on rows that
    # were inserted before Phase #96 introduced them. For cloze mode we
    # also fill sample_sentence on demand from the user's saved texts
    # and drop any row that has no containing sentence — cloze only
    # makes sense if we can show the word in real context.
    backfilled = False
    cards = []
    for r in rows:
        enriched = _enrich(r)
        if (not r.pinyin and enriched["pinyin"]) or (not r.meaning and enriched["meaning"]):
            r.pinyin = enriched["pinyin"] or None
            r.meaning = enriched["meaning"] or None
            backfilled = True

        sentence: str | None = None
        if mode == "cloze":
            sentence = r.sample_sentence or cloze.populate_sample_sentence(r, db)
            if sentence:
                backfilled = True
            else:
                # Skip rows that have no sample sentence — cloze requires
                # one, and other modes will still cover them.
                continue

        card = {
            "word": to_user_script(r.word, user),
            "due_at": r.due_at.isoformat() if r.due_at else None,
            "stability": r.stability,
            "difficulty": r.difficulty,
            **enriched,
        }
        if mode == "cloze" and sentence:
            displayed_sentence = to_user_script(sentence, user)
            displayed_word = to_user_script(r.word, user)
            card["cloze_template"] = cloze.make_cloze_template(displayed_sentence, displayed_word)
            card["cloze_sentence"] = displayed_sentence
        cards.append(card)
    if backfilled:
        db.commit()
    return {"mode": mode, "cards": cards}


@router.post("/api/review/grade")
async def grade_card(
    payload: GradeRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    if payload.grade not in srs.VALID_GRADES:
        raise HTTPException(status_code=400, detail=f"grade must be one of {srs.VALID_GRADES}")

    # If the user is on a non-auto display script, the word came back to
    # us in their preferred form. UserWord rows are keyed by simp.
    from app.services.script import to_canonical

    word_simp = to_canonical(payload.word, user)

    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word_simp).first()
    if row is None:
        # Auto-promote: grading a word we've never seen creates the row.
        row = UserWord(user_id=user.id, word=word_simp, state="learning", seen_count=1)
        db.add(row)

    updated = srs.apply_grade(row.fsrs_state, payload.grade, retention=user.review_retention)
    row.fsrs_state = updated["fsrs_state"]
    row.stability = updated["stability"]
    row.difficulty = updated["difficulty"]
    row.due_at = updated["due_at"]
    row.last_reviewed_at = updated["last_reviewed_at"]
    row.updated_at = datetime.utcnow()

    # Auto-transition between 'learning' and 'known' based on the new
    # FSRS stability. Crossing into 'known' = mastered (renders as
    # known-color in the reader); dropping below = back into active
    # learning. State flips are emitted as state_change events so the
    # log captures the inflection (helps with stats + undo).
    new_state_for_row = (
        "known" if (row.stability or 0) >= KNOWN_STABILITY_THRESHOLD_DAYS else "learning"
    )
    if new_state_for_row != row.state and row.state in ACTIVE_REVIEW_STATES:
        row.state = new_state_for_row
        db.add(
            UserWordEvent(
                user_id=user.id,
                word=word_simp,
                event_type="state_change",
                new_state=new_state_for_row,
            )
        )

    db.add(
        UserWordEvent(
            user_id=user.id,
            word=word_simp,
            event_type="review",
            new_state=row.state,
            grade=payload.grade,
        )
    )
    record_activity(user, db)
    db.commit()
    return {
        "word": to_user_script(word_simp, user),
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
            UserWord.state.in_(ACTIVE_REVIEW_STATES),
            or_(UserWord.due_at.is_(None), UserWord.due_at <= now),
        )
        .count()
    )
    due_today = (
        db.query(UserWord)
        .filter(
            UserWord.user_id == user.id,
            UserWord.state.in_(ACTIVE_REVIEW_STATES),
            or_(
                UserWord.due_at.is_(None),
                UserWord.due_at < midnight_tomorrow,
            ),
        )
        .count()
    )
    # The "learning" counter excludes the 'known' bucket so the user can
    # distinguish "still struggling" from "mastered but still in rotation".
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
