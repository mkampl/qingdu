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
- cloze:       only cards with a sample sentence; the SPA blanks the word.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWord, UserWordEvent, get_db
from app.services import cloze, readability, review_scope, srs, tone_drill, user_words
from app.services.cedict_loader import cap_meanings
from app.services.due import (
    ACTIVE_REVIEW_STATES,
    due_clause,
    end_of_day,
    review_window_clause,
    utcnow,
)
from app.services.enrollment import enroll_daily_words, enrolled_today
from app.services.localday import start_of_today, user_tz
from app.services.readings import readings_payload
from app.services.script import to_canonical, to_user_script
from app.services.streak import record_activity
from app.services.timestamps import iso_utc
from app.services.word_info import cedict_entry, lookup_pinyin_meaning
from app.state import hsk_vocab

router = APIRouter(tags=["Review"])

ReviewMode = Literal["recognition", "dictation", "writing", "cloze"]
# Queue can also be fetched in "mixed" — one queue that carries the data for
# all four modalities so the frontend can cycle a single card through every
# mode without re-fetching. Grading endpoint still requires a real mode.
QueueMode = Literal["recognition", "dictation", "writing", "cloze", "mixed"]


class GradeRequest(BaseModel):
    word: str
    grade: int  # 1=Again, 2=Hard, 3=Good, 4=Easy
    mode: ReviewMode = "recognition"
    # Accepted and ignored, so older clients that send it keep working.
    cycle: bool = False


def _enrich(row: UserWord) -> dict:
    """
    Pinyin + meaning for the queue payload. Prefer the snapshot stored on
    the UserWord row (it keeps a package's meaning); fall back to the
    dictionary for rows without one. The queue handler writes the
    looked-up values back to the row.
    """
    pinyin = row.pinyin or ""
    meaning = row.meaning or ""
    entry = hsk_vocab.get(row.word)
    cedict_hit, _ = cedict_entry(row.word)
    # Prefer the meanings list from the richer source: HSK entries already
    # have CC-CEDICT meanings overlaid at startup, so hsk_vocab is the
    # primary; cedict_vocab covers non-HSK literary/proper-noun terms.
    source_entry = entry or cedict_hit or {}
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

    # Tagged glosses in creation order, so the dictionary entry (always
    # seeded first) lands at index 0 and package entries follow. The
    # frontend shows them with provenance chips ("[Dao De Jing]").
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
        # Every reading of a polyphone for the card back, the one this
        # card is graded on (its stored pinyin) marked main.
        "readings": readings_payload(source_entry, main_pinyin=pinyin),
        "hsk_level": hsk_level,
        "glosses": glosses_payload,
    }


def _card(row: UserWord, user: User, db: Session) -> dict:
    """The card payload shared by the review queue and practice."""
    enriched = _enrich(row)
    # The context the word was met in, else one from a saved or library
    # text: cloze blanks it, the other surfaces show it once the answer
    # is out.
    sentence = row.sample_sentence or cloze.populate_sample_sentence(row, db)
    card = {
        "word": to_user_script(row.word, user),
        "due_at": iso_utc(row.due_at),
        "stability": row.stability,
        "difficulty": row.difficulty,
        # Progressive prompt stage from FSRS stability and the user's
        # review focus (intro / read / trace / produce; see srs.py).
        "prompt_stage": srs.stage_for_row(row, user),
        # Seconds to the next review after each grade (1-4), for the buttons.
        "intervals": srs.next_intervals(row.fsrs_state, user.review_retention),
        "has_sample_sentence": bool(sentence),
        **enriched,
    }
    if sentence:
        displayed_sentence = to_user_script(sentence, user)
        displayed_word = to_user_script(row.word, user)
        card["cloze_template"] = cloze.make_cloze_template(displayed_sentence, displayed_word)
        card["cloze_sentence"] = displayed_sentence
        card["sentence_source"] = row.sample_source
    return card


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
    text_key: str | None = Query(None, max_length=200),
    list_id: int | None = None,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    Return up to `limit` cards due within the user's review window, or
    with no due_at yet (they need a first FSRS init). Ordered by due_at
    ASC, NULLs first.

    Side effect: tops up the user's 'learning' pool with up to
    `daily_new_words` fresh HSK entries before reading the queue, so the
    queue never goes empty while there are HSK words left to learn.

    `text_key` or `list_id` focus the session on the words pre-learned for
    one text or the words of one vocab list (services.review_scope). Such
    a session enrols no new words, and each card names the text's or
    list's own meaning as `focus_gloss`.

    Plain `def`: everything in here is sync DB work, so FastAPI runs it
    in the threadpool instead of blocking the event loop.
    """
    now = utcnow()
    tz = user_tz(user)
    scope = review_scope.resolve(db, user, text_key, list_id)
    if scope is None and enroll_daily_words(user, db, now):
        db.commit()
    # The user's look-ahead window (users.review_window). services.due owns
    # the definition; /api/review/stats counts with it.
    base = db.query(UserWord).filter(
        UserWord.user_id == user.id, review_window_clause(user.review_window, now, tz)
    )
    if scope is not None:
        base = base.filter(scope.clause)
    base = base.order_by(UserWord.due_at.is_(None).desc(), UserWord.due_at.asc(), UserWord.id.asc())
    # Cloze drops rows without a sentence, so a plain LIMIT could hand
    # back an empty queue while eligible cards sit further down. Page
    # through the due rows until `limit` cards survive the filter.
    rows = _cloze_candidates(base, limit, db) if mode == "cloze" else base.limit(limit).all()
    # Rows without a pinyin/meaning snapshot get the looked-up values.
    cards = []
    for r in rows:
        card = _card(r, user, db)
        if (not r.pinyin and card["pinyin"]) or (not r.meaning and card["meaning"]):
            r.pinyin = card["pinyin"] or None
            r.meaning = card["meaning"] or None
        card["focus_gloss"] = review_scope.focus_gloss(scope, r)
        cards.append(card)
    # Snapshot backfill and freshly found cloze sentences.
    if db.dirty:
        db.commit()
    return {"mode": mode, "cards": cards, "scope_title": scope.title if scope else None}


@router.get("/api/review/practice/{word}")
def practice_card(
    word: str,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """One tracked word as a practice card, whether due or not.

    Same payload as a review-queue card. Practice is not graded and does
    not touch FSRS, the streak or the stats."""
    # /words lists words in the user's display script; rows are canonical.
    word = to_canonical(word, user)
    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not a tracked word")
    card = _card(row, user, db)
    # populate_sample_sentence may have stored a sentence; commit it so a
    # follow-up practice call doesn't look it up again.
    db.commit()
    return {"card": card}


@router.post("/api/review/grade")
def grade_card(
    payload: GradeRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Grade one review card: one grade, one FSRS step. `mode` is logged
    with the review event."""
    if payload.grade not in srs.VALID_GRADES:
        raise HTTPException(status_code=400, detail=f"grade must be one of {srs.VALID_GRADES}")

    # If the user is on a non-auto display script, the word came back to
    # us in their preferred form. UserWord rows are keyed by simp.
    word_simp = to_canonical(payload.word, user)

    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word_simp).first()
    # Only cards the queue could have handed out are gradeable: no rows
    # for arbitrary strings, no grading (or streak) for ignored words.
    if row is None:
        raise HTTPException(status_code=404, detail="Not a tracked word")
    if row.state not in ACTIVE_REVIEW_STATES:
        raise HTTPException(status_code=409, detail="This word is not in your review rotation")

    user_words.grade_word(db, row, payload.grade, payload.mode, user.review_retention)
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
        "prompt_stage": srs.stage_for_row(row, user),
    }


@router.get("/api/review/stats")
def review_stats(
    text_key: str | None = Query(None, max_length=200),
    list_id: int | None = None,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    Summary for the nav badge + ReviewView dashboard.
    - `due_now`: cards currently due (due_at <= now).
    - `due_today`: cards due before the end of the user's local today.
    - `due_in_window`: what /api/review/queue would serve right now under
      the user's review_window — the badge and the Start gate read this.
    - `learning`: total cards in the 'learning' state.
    - `in_rotation`: learning + known cards (everything that can come due).
    - `reviewed_today`: reviews logged since local midnight.

    - `scope`: with `text_key` or `list_id`, the focused session's title,
      its words in rotation (`total`), how many of them are due under the
      review window (`due`), now (`due_now`) and today (`due_today`), and
      how many already count as learned (`learned`).

    "Today" is the user's local day (services.localday, users.timezone).
    """
    now = utcnow()
    tz = user_tz(user)
    midnight_today = start_of_today(now, tz)

    def count(*criteria) -> int:
        return db.query(UserWord).filter(UserWord.user_id == user.id, *criteria).count()

    due_now = count(review_window_clause("now", now))
    # Same definition as the /words "Due today" chip (services.due).
    due_today = count(due_clause(end_of_day(now, 0, tz)))
    due_in_window = count(review_window_clause(user.review_window, now, tz))
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
    scope = review_scope.resolve(db, user, text_key, list_id)
    scope_counts = None
    if scope is not None:
        rows = (
            db.query(UserWord.state, UserWord.stability)
            .filter(
                UserWord.user_id == user.id,
                UserWord.state.in_(ACTIVE_REVIEW_STATES),
                scope.clause,
            )
            .all()
        )
        scope_counts = {
            "title": scope.title,
            "due": count(review_window_clause(user.review_window, now, tz), scope.clause),
            "total": len(rows),
            "due_now": count(review_window_clause("now", now), scope.clause),
            "due_today": count(due_clause(end_of_day(now, 0, tz)), scope.clause),
            # Learned = counts as known when reading (services.readability).
            "learned": sum(
                1 for state, stab in rows if readability.classify(state, stab) == "known"
            ),
        }
    return {
        "scope": scope_counts,
        "due_now": due_now,
        "due_today": due_today,
        "due_in_window": due_in_window,
        "learning": learning,
        "in_rotation": in_rotation,
        "reviewed_today": reviewed_today,
        # Counters for the "new today: X / Y" badge.
        "new_today": enrolled_today(user, db, now),
        "daily_target": user.daily_new_words or 0,
    }


@router.get("/api/review/tones")
def tone_practice(
    n: int = Query(12, ge=1, le=tone_drill.MAX_ITEMS),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Tone practice items: a word to hear and pinyin choices that differ
    only in tone (services.tone_drill). Practice only, nothing is graded."""
    return {"items": tone_drill.build(db, user.id, n)}
