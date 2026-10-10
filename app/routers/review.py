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

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWord, UserWordEvent, get_db
from app.services import cloze, srs
from app.services.cedict_loader import cap_meanings
from app.services.due import (
    ACTIVE_REVIEW_STATES,
    due_clause,
    end_of_day,
    review_window_clause,
)
from app.services.enrollment import enroll_daily_words, enrolled_today
from app.services.script import to_canonical, to_user_script
from app.services.streak import record_activity
from app.services.timestamps import iso_utc
from app.services.word_info import lookup_pinyin_meaning
from app.state import cedict_vocab, hsk_vocab

router = APIRouter(tags=["Review"])

# ACTIVE_REVIEW_STATES (from services.due) are the states in the review
# rotation. Auto-transitions in grade_card move rows between 'learning'
# and 'known' based on the FSRS stability after grading.
KNOWN_STABILITY_THRESHOLD_DAYS = 90.0


def next_state_after_grade(state: str, stability: float | None, grade: int) -> str:
    """Learning/known transition after one grade (hysteresis).

    learning → known once stability reaches KNOWN_STABILITY_THRESHOLD_DAYS.
    known → learning only on Again; Hard/Good/Easy keep a known card known.
    """
    if state == "known":
        return "learning" if grade == 1 else "known"
    if (stability or 0) >= KNOWN_STABILITY_THRESHOLD_DAYS:
        return "known"
    return "learning"


ReviewMode = Literal["recognition", "dictation", "writing", "cloze"]
# Queue can also be fetched in "mixed" — one queue that carries the data for
# all four modalities so the frontend can cycle a single card through every
# mode without re-fetching. Grading endpoint still requires a real mode.
QueueMode = Literal["recognition", "dictation", "writing", "cloze", "mixed"]


class GradeRequest(BaseModel):
    word: str
    grade: int  # 1=Again, 2=Hard, 3=Good, 4=Easy
    mode: ReviewMode = "recognition"
    # Phase 1.3 introduced a cycle-gating flag; Phase 1.3b reverted to
    # single-FSRS-advance and uses prompt_stage instead. Field stays in
    # the schema for client back-compat — any value is accepted and
    # ignored. New clients should omit it.
    cycle: bool = False


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
    source_entry = entry or cedict_entry or {}
    meanings = source_entry.get("meanings", []) or []
    hsk_level = entry.get("level") if entry else None

    if not pinyin or not meaning:
        looked_up_pinyin, looked_up_meaning = lookup_pinyin_meaning(row.word)
        if not pinyin:
            pinyin = looked_up_pinyin
        if not meaning:
            meaning = looked_up_meaning

    # Cap the alternatives shown on a review card. CC-CEDICT frequently
    # ships 10+ etymologically-ordered senses (零 has 12: "zero, nought,
    # zero sign, fractional, ..., to wither"); showing them all under
    # the primary reading distracts from the everyday meaning. The cap
    # counts senses other than the headline's own, which the card hides
    # (the headline is not always meanings[0]). Analysis / popovers read
    # the vocab dicts directly, so they still see the full list.
    meanings = cap_meanings(meaning, meanings, 4)

    if not meanings and meaning:
        meanings = [meaning]

    # Register tags only belong to the dictionary headline; a curated
    # package/glossary meaning on the row gets none.
    meaning_tags = (
        list(source_entry.get("meaning_tags") or [])
        if meaning and meaning == source_entry.get("meaning")
        else []
    )

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
        "meaning_tags": meaning_tags,
        "hsk_level": hsk_level,
        "glosses": glosses_payload,
    }


_CLOZE_PAGE_SIZE = 50


def _cloze_candidates(query, limit: int, db: Session) -> list[UserWord]:
    """First `limit` rows of `query` that have (or can be given) a sample
    sentence. Rows without one are skipped; misses are cached by
    services.cloze, so re-scans stay cheap."""
    picked: list[UserWord] = []
    offset = 0
    while len(picked) < limit:
        page = query.offset(offset).limit(_CLOZE_PAGE_SIZE).all()
        if not page:
            break
        offset += len(page)
        for row in page:
            if row.sample_sentence or cloze.populate_sample_sentence(row, db):
                picked.append(row)
                if len(picked) >= limit:
                    break
    return picked


@router.get("/api/review/queue")
def review_queue(
    mode: QueueMode = "recognition",
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

    Plain `def`: everything in here is sync DB work, so FastAPI runs it
    in the threadpool instead of blocking the event loop.
    """
    enrolled = enroll_daily_words(user, db)
    if enrolled:
        db.commit()
    now = datetime.utcnow()
    # Phase #119 — look-ahead window. People review once a day, not every
    # 30 minutes; widening the cutoff to "today" covers the typical session
    # without forcing the user to wait for each card to flip due. Strict
    # FSRS-conformant pull is still available via review_window='now'.
    # services.due owns the definition; /api/review/stats counts with it.
    base = (
        db.query(UserWord)
        .filter(UserWord.user_id == user.id, review_window_clause(user.review_window, now))
        .order_by(UserWord.due_at.is_(None).desc(), UserWord.due_at.asc(), UserWord.id.asc())
    )
    # Cloze drops rows without a sentence, so a plain LIMIT could hand
    # back an empty queue while eligible cards sit further down. Page
    # through the due rows until `limit` cards survive the filter.
    rows = _cloze_candidates(base, limit, db) if mode == "cloze" else base.limit(limit).all()
    # Build payload and lazy-backfill the snapshot columns on rows that
    # were inserted before Phase #96 introduced them. Cloze rows arrive
    # with a sample sentence already filled in (_cloze_candidates); other
    # modes (mixed included — it never renders a cloze step) only pass
    # along a sentence that is already cached on the row.
    cards = []
    for r in rows:
        enriched = _enrich(r)
        if (not r.pinyin and enriched["pinyin"]) or (not r.meaning and enriched["meaning"]):
            r.pinyin = enriched["pinyin"] or None
            r.meaning = enriched["meaning"] or None

        sentence: str | None = r.sample_sentence

        # Phase 1.3b — progressive prompt stage picked from FSRS stability.
        # intro for fresh / unreviewed cards (full info + auto-pass),
        # trace once the card has any stability < 10d (hanzi-writer
        # production with pinyin cues), produce once stability ≥ 10d
        # (pinyin + meaning only, recall + reveal + self-grade).
        stage = srs.prompt_stage_for(r.stability)

        card = {
            "word": to_user_script(r.word, user),
            "due_at": iso_utc(r.due_at),
            "stability": r.stability,
            "difficulty": r.difficulty,
            "prompt_stage": stage,
            "has_sample_sentence": bool(sentence),
            **enriched,
        }
        if sentence:
            displayed_sentence = to_user_script(sentence, user)
            displayed_word = to_user_script(r.word, user)
            card["cloze_template"] = cloze.make_cloze_template(displayed_sentence, displayed_word)
            card["cloze_sentence"] = displayed_sentence
        cards.append(card)
    # Snapshot backfill and freshly found cloze sentences.
    if db.dirty:
        db.commit()
    return {"mode": mode, "cards": cards}


@router.get("/api/review/practice/{word}")
def practice_card(
    word: str,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch a single UserWord as a practice card.

    Same enrichment as the review queue, but no auto-enrol, no due-date
    filter, no ordering. The client uses this to let the user cycle
    through a specific word's four modalities without any server-side
    FSRS / streak / stats mutation — practice is deliberately 'aus der
    Konkurrenz raus'. Nothing is graded, so there's no matching
    /api/review/grade sibling; the SPA advances modes locally and
    returns to /words on End Practice."""
    # /words lists words in the user's display script; rows are canonical.
    word = to_canonical(word, user)
    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not a tracked word")
    enriched = _enrich(row)
    sentence = row.sample_sentence or cloze.populate_sample_sentence(row, db)
    stage = srs.prompt_stage_for(row.stability)
    card = {
        "word": to_user_script(row.word, user),
        "due_at": iso_utc(row.due_at),
        "stability": row.stability,
        "difficulty": row.difficulty,
        "prompt_stage": stage,
        "has_sample_sentence": bool(sentence),
        **enriched,
    }
    if sentence:
        displayed_sentence = to_user_script(sentence, user)
        displayed_word = to_user_script(row.word, user)
        card["cloze_template"] = cloze.make_cloze_template(displayed_sentence, displayed_word)
        card["cloze_sentence"] = displayed_sentence
    # populate_sample_sentence may have written a new snapshot; commit that
    # so a follow-up practice call doesn't do the lookup again.
    db.commit()
    return {"card": card}


@router.post("/api/review/grade")
def grade_card(
    payload: GradeRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Grade one review card. Phase 1.3b — single FSRS advance per grade.
    The card's prompt stage (intro / trace / produce) is picked by
    `srs.prompt_stage_for(stability)` on the queue side, so the grade
    endpoint stays simple: one grade, one FSRS step. The Mixed-mode
    cycle that Phase 1.3 introduced is gone; the schema columns remain
    for event telemetry only.
    """
    if payload.grade not in srs.VALID_GRADES:
        raise HTTPException(status_code=400, detail=f"grade must be one of {srs.VALID_GRADES}")

    # If the user is on a non-auto display script, the word came back to
    # us in their preferred form. UserWord rows are keyed by simp.
    word_simp = to_canonical(payload.word, user)

    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word_simp).first()
    # Only cards the queue could have handed out are gradeable. Grading
    # used to create rows for arbitrary strings and to advance (and
    # streak-bump) ignored words.
    if row is None:
        raise HTTPException(status_code=404, detail="Not a tracked word")
    if row.state not in ACTIVE_REVIEW_STATES:
        raise HTTPException(status_code=409, detail="This word is not in your review rotation")

    updated = srs.apply_grade(row.fsrs_state, payload.grade, retention=user.review_retention)
    row.fsrs_state = updated["fsrs_state"]
    row.stability = updated["stability"]
    row.difficulty = updated["difficulty"]
    row.due_at = updated["due_at"]
    row.last_reviewed_at = updated["last_reviewed_at"]
    row.updated_at = datetime.utcnow()

    # Auto-transition between 'learning' and 'known' based on the new
    # FSRS stability. Crossing into 'known' = mastered (renders as
    # known-color in the reader). The way back is deliberately narrower:
    # only a lapse (Again) demotes a known card. FSRS's same-day formula
    # can drop stability far below the threshold on a plain Hard (90 →
    # ~41), and that is not the user saying "I forgot this word".
    # State flips are emitted as state_change events so the log captures
    # the inflection (helps with stats + undo).
    new_state_for_row = next_state_after_grade(row.state, row.stability, payload.grade)
    if new_state_for_row != row.state:
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
            mode=payload.mode,
        )
    )
    record_activity(user, db)
    db.commit()
    return {
        "word": to_user_script(word_simp, user),
        "due_at": iso_utc(row.due_at),
        "stability": row.stability,
        "difficulty": row.difficulty,
        # The card's new prompt stage given the just-updated stability —
        # informational, the SPA uses it to pre-render the next-cards
        # surfaces without a second fetch.
        "prompt_stage": srs.prompt_stage_for(row.stability),
    }


@router.get("/api/review/stats")
def review_stats(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    Summary for the nav badge + ReviewView dashboard.
    - `due_now`: cards currently due (due_at <= now).
    - `due_today`: cards due before the end of today (UTC).
    - `due_in_window`: what /api/review/queue would serve right now under
      the user's review_window — the badge and the Start gate read this.
    - `learning`: total cards in the 'learning' state.
    - `in_rotation`: learning + known cards (everything that can come due).
    - `reviewed_today`: reviews logged since UTC midnight.
    """
    now = datetime.utcnow()
    midnight_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def count(*criteria) -> int:
        return db.query(UserWord).filter(UserWord.user_id == user.id, *criteria).count()

    due_now = count(review_window_clause("now", now))
    # Same definition as the /words "Due today" chip (services.due).
    due_today = count(due_clause(end_of_day(now)))
    due_in_window = count(review_window_clause(user.review_window, now))
    # The "learning" counter excludes the 'known' bucket so the user can
    # distinguish "still struggling" from "mastered but still in rotation".
    learning = count(UserWord.state == "learning")
    in_rotation = count(UserWord.state.in_(ACTIVE_REVIEW_STATES))
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
        "due_in_window": due_in_window,
        "learning": learning,
        "in_rotation": in_rotation,
        "reviewed_today": reviewed_today,
        # Phase #96 — counters for the "new today: X / Y" badge.
        "new_today": enrolled_today(user, db),
        "daily_target": user.daily_new_words or 0,
    }
