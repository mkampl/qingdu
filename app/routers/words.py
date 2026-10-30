"""
Per-user word-state tracking: LingQ-style "known words" and the SRS
review rotation. Routes here let the SPA read and change each user's word
states and read aggregate stats.

State model:
- Absence of a UserWord row == 'new' (never touched).
- A row's `state` column is one of {'learning', 'known', 'ignored'}.
- Clicking a word in the reader bumps 'new' → 'learning' (handled here);
  explicit toggles in the popover write 'known' or 'ignored'.

Every mutation also appends a UserWordEvent (the activity stats read it).
"""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWord, get_db
from app.schemas import (
    VALID_WORD_STATES,
    BulkMarkKnownRequest,
    ImportHskRequest,
    ReviewNowRequest,
    SnoozeRequest,
    WordStateUpdate,
)
from app.services import cloze, user_words
from app.services.due import due_clause, end_of_day, utcnow
from app.services.levels import level_number
from app.services.lexicon import is_lexical_word, user_word_sources
from app.services.localday import user_tz
from app.services.script import to_canonical, to_user_script
from app.services.srs import ALREADY_KNOWN_STABILITY_DAYS
from app.services.streak import current_streak, record_activity
from app.services.timestamps import iso_utc
from app.services.word_search import search_clause
from app.state import hsk_vocab

router = APIRouter(tags=["Words"])


def not_a_word_detail(word: str) -> str:
    return f"「{word}」 is not a dictionary word. Save the words it is made of instead."


@router.get("/api/words/state")
async def list_word_states(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the user's full state map: { word: 'learning'|'known'|'ignored' }.
    Sized for the typical user (a few thousand entries), so we ship the whole
    thing instead of paging. The frontend caches it in a Pinia store.
    """
    rows = db.query(UserWord.word, UserWord.state).filter(UserWord.user_id == user.id).all()
    return {"states": dict(rows)}


@router.post("/api/words/state")
async def set_word_state(
    payload: WordStateUpdate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    if payload.state not in VALID_WORD_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state '{payload.state}'")
    word = to_canonical(payload.word.strip(), user)
    if not word:
        raise HTTPException(status_code=400, detail="word is required")
    is_pkg = payload.translation_source == "package" and bool(payload.meaning or payload.pinyin)
    if not user_words.may_create_word(db, user.id, word, is_pkg=is_pkg):
        raise HTTPException(status_code=422, detail=not_a_word_detail(word))

    row = user_words.upsert_word(
        db,
        user.id,
        word,
        payload.state,
        payload.source_text_id,
        pkg_meaning=payload.meaning,
        pkg_pinyin=payload.pinyin,
        pkg_translation_source=payload.translation_source,
        pkg_source_tag=payload.package_source,
    )
    if payload.sentence:
        cloze.adopt_sentence(
            row,
            to_canonical(payload.sentence, user),
            user_words.context_title(db, user.id, payload.source_text_id, payload.library_slug),
        )
    record_activity(user, db)
    db.commit()
    # The scheduling fields let a list view patch its row with what the
    # server actually did (marking known reschedules due_at 60-180 d out).
    return {"word": word, "state": payload.state, **_schedule_fields(row, utcnow())}


@router.delete("/api/words/state")
async def clear_word_state(
    word: str,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Reset a word back to 'new' (delete the row). Useful for 'undo'."""
    word = to_canonical(word, user)
    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word).first()
    if row is not None:
        db.delete(row)
        user_words.record_event(db, user.id, word, "state_change", None, None)
        db.commit()
    return {"word": word, "state": "new"}


@router.post("/api/words/bulk-mark-known")
async def bulk_mark_known(
    payload: BulkMarkKnownRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    Promote a batch of words to 'known'. Used by the page-complete /
    section-complete LingQ-style action. Idempotent: words already known are
    no-ops; words in other states are overwritten. Words that are not
    dictionary words (phrases from texts analysed before they were split)
    are skipped and listed under `skipped`.
    """
    # Dedup at the boundary — callers may include the same word twice (e.g.
    # multiple sentences in the same section). Without this we'd try to
    # insert the same (user_id, word) row twice and trip the unique index.
    seen: set[str] = set()
    words: list[str] = []
    for w in payload.words:
        if not w:
            continue
        stripped = to_canonical(w.strip(), user)
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        words.append(stripped)
    if not words:
        return {"updated": 0, "total": 0, "skipped": []}

    existing = {
        r.word: r
        for r in db.query(UserWord)
        .filter(UserWord.user_id == user.id, UserWord.word.in_(words))
        .all()
    }
    # Resolve a per-word package snapshot, if one was supplied. The
    # mapping is keyed by canonical surface form so it survives the
    # to_canonical() pass above.
    snapshots = payload.snapshots or {}
    updated = 0
    skipped: list[str] = []
    own_words: set[str] | None = None
    for word in words:
        snap = snapshots.get(word)
        pkg_meaning = snap.meaning if snap else None
        pkg_pinyin = snap.pinyin if snap else None
        pkg_source = snap.translation_source if snap else None
        pkg_tag = snap.package_source if snap else None
        is_pkg = pkg_source == "package" and (pkg_meaning or pkg_pinyin) is not None

        row = existing.get(word)
        if row is None and not is_pkg and not is_lexical_word(word):
            if own_words is None:
                own_words = user_word_sources(db, user.id)
            if word not in own_words:
                skipped.append(word)
                continue
        if row is None:
            row = UserWord(user_id=user.id, word=word, state="learning", seen_count=1)
            user_words.apply_known_scheduling(row)
            db.add(row)
            db.flush()
            updated += 1
        elif (row.stability or 0) < ALREADY_KNOWN_STABILITY_DAYS:
            user_words.apply_known_scheduling(row)
            row.updated_at = datetime.utcnow()
            updated += 1

        user_words.seed_glosses(db, row, word, is_pkg, pkg_pinyin, pkg_meaning, pkg_tag)
        user_words.record_event(
            db, user.id, word, "bulk_mark_known", "known", payload.source_text_id
        )
    record_activity(user, db)
    db.commit()
    return {"updated": updated, "total": len(words), "skipped": skipped}


@router.get("/api/words/stats")
async def word_stats(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Aggregate counts for the header badge + streak."""
    rows = db.query(UserWord.state).filter(UserWord.user_id == user.id).all()
    counts = {"learning": 0, "known": 0, "ignored": 0}
    for (state,) in rows:
        if state in counts:
            counts[state] += 1
    counts["streak"] = current_streak(user)
    counts["streak_freezes"] = user.streak_freeze_count or 0
    return counts


@router.post("/api/words/import-hsk")
async def import_hsk_known(
    payload: ImportHskRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """
    "I already know HSK 1–N" onboarding shortcut. Bulk-inserts every word
    at level <= up_to_level as 'known'. Idempotent — words the user has
    already touched are left alone (we don't overwrite 'ignored' or
    'learning' silently; the intent of this action is "fill the void").
    """
    if payload.hsk_version not in {"new", "old"}:
        raise HTTPException(status_code=400, detail="hsk_version must be 'new' or 'old'")
    max_level = 9 if payload.hsk_version == "new" else 6
    if not 1 <= payload.up_to_level <= max_level:
        raise HTTPException(
            status_code=400,
            detail=f"up_to_level must be 1..{max_level} for HSK {payload.hsk_version}",
        )

    return user_words.import_hsk_known(db, user, payload.up_to_level, payload.hsk_version)


def _hsk_level(entry: dict | None, hsk_version: str = "new") -> int | None:
    """Numeric HSK level of a hsk_vocab entry for the chosen HSK version.

    Mirrors the reader's levelForVersion(): the preferred version's level,
    falling back to the other one when the word only exists in that list.
    """
    if not entry:
        return None
    first, second = (
        ("level_old", "level_new") if hsk_version == "old" else ("level_new", "level_old")
    )
    lvl = level_number(entry.get(first), ("new-", "old-"))
    if lvl is None:
        lvl = level_number(entry.get(second), ("new-", "old-"))
    return lvl


def _schedule_fields(row: UserWord, now: datetime) -> dict:
    """The FSRS fields of a row as the /words list shows them."""
    return {
        "due_at": iso_utc(row.due_at),
        "seconds_until_due": int((row.due_at - now).total_seconds()) if row.due_at else None,
        "stability": row.stability,
        "difficulty": row.difficulty,
        "last_reviewed_at": iso_utc(row.last_reviewed_at),
    }


@router.get("/api/words/queue")
async def list_queue(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    state: str | None = None,
    due_within_days: int | None = None,
    hsk_levels: str | None = None,
    hsk_version: str = "new",
    search: str | None = None,
    sort: str = "due",
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """Personal SRS queue browser.

    Filters:
      - state: comma-separated subset of {learning, known, ignored}
      - due_within_days: rows due before the end of the day N days from now,
        with the definition the Review page uses (services.due): 0 is the
        Review page's "due today". Ignored rows are never due;
        never-scheduled learning/known rows always are.
      - hsk_levels: comma-separated HSK levels like "1,2,3" — matched against the
        global hsk_vocab map, using `hsk_version` ("new" or "old")
      - search: hanzi (either script), pinyin (tones optional) or meaning
    sort: 'due' (NULL last), 'recent' (newest first), 'hsk' (lowest level first)
    Paging: limit is clamped to 1..500, offset to >= 0. `total` counts every
    row matching the filters; `has_more` says whether a later page exists.
    Words come back in the user's display script, like /api/review.
    """
    if hsk_version not in {"new", "old"}:
        raise HTTPException(400, "hsk_version must be 'new' or 'old'")

    now = utcnow()
    q = db.query(UserWord).filter(UserWord.user_id == user.id)

    if state:
        wanted = {s.strip() for s in state.split(",") if s.strip()}
        if wanted - VALID_WORD_STATES:
            raise HTTPException(400, f"unknown state in {wanted - VALID_WORD_STATES}")
        q = q.filter(UserWord.state.in_(wanted))

    if due_within_days is not None and due_within_days >= 0:
        q = q.filter(due_clause(end_of_day(now, due_within_days, user_tz(user))))

    if search and (clause := search_clause(search, user)) is not None:
        q = q.filter(clause)

    wanted_lvls: set[int] = set()
    if hsk_levels:
        try:
            wanted_lvls = {int(s) for s in hsk_levels.split(",") if s.strip()}
        except ValueError as e:
            raise HTTPException(400, "hsk_levels must be comma-separated ints") from e

    # HSK filter and HSK sort both run in SQL so `total`, LIMIT and OFFSET
    # see the same row set. The word -> level map is shipped as a single
    # JSON parameter and expanded with json_each(), which sidesteps
    # SQLite's bound-variable limit (the full vocab is ~13k words).
    level_col = None
    if wanted_lvls or sort == "hsk":
        level_map = {
            w: lvl
            for w, entry in hsk_vocab.items()
            if (lvl := _hsk_level(entry, hsk_version)) is not None
            and (sort == "hsk" or lvl in wanted_lvls)
        }
        lv = (
            func.json_each(json.dumps(level_map, ensure_ascii=False))
            .table_valued("key", "value")
            .alias("hsk_lv")
        )
        if wanted_lvls:
            q = q.join(lv, lv.c.key == UserWord.word).filter(lv.c.value.in_(wanted_lvls))
        else:
            q = q.outerjoin(lv, lv.c.key == UserWord.word)
        level_col = lv.c.value

    if sort == "recent":
        q = q.order_by(UserWord.created_at.desc(), UserWord.id.desc())
    elif sort == "hsk" and level_col is not None:
        # Lowest level first, words outside HSK last, oldest first within a level.
        q = q.order_by(
            level_col.is_(None), level_col.asc(), UserWord.created_at.asc(), UserWord.id.asc()
        )
    else:  # 'due' default — due-now first, then upcoming, NULLs last
        q = q.order_by(UserWord.due_at.is_(None), UserWord.due_at.asc(), UserWord.id.asc())

    limit = max(1, min(limit, 500))
    offset = max(offset, 0)
    total = q.count()
    rows = q.limit(limit).offset(offset).all()

    items = [
        {
            "word": to_user_script(r.word, user),
            "state": r.state,
            "pinyin": r.pinyin,
            "meaning": r.meaning,
            "hsk_level": _hsk_level(hsk_vocab.get(r.word), hsk_version),
            "seen_count": r.seen_count,
            "ease": r.ease,
            **_schedule_fields(r, now),
            "created_at": iso_utc(r.created_at),
        }
        for r in rows
    ]
    return {"items": items, "total": total, "has_more": offset + len(items) < total}


@router.post("/api/words/snooze")
async def snooze_word(
    payload: SnoozeRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Push a word's due date `days` (1-365, default 3) forward."""
    word_raw = payload.word.strip()
    days = payload.days
    if not word_raw:
        raise HTTPException(400, "word is required")

    word = to_canonical(word_raw, user)
    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word).first()
    if row is None:
        raise HTTPException(404, "word not in your queue")

    now = utcnow()
    base = max(row.due_at or now, now)
    row.due_at = base + timedelta(days=days)
    user_words.record_event(db, user.id, word, "snooze")
    db.commit()
    return {"word": word, "days": days, **_schedule_fields(row, now)}


@router.post("/api/words/review-now")
async def review_now(
    payload: ReviewNowRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Set due_at = now so the word surfaces immediately in /review."""
    word_raw = payload.word.strip()
    if not word_raw:
        raise HTTPException(400, "word is required")
    word = to_canonical(word_raw, user)
    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word).first()
    if row is None:
        raise HTTPException(404, "word not in your queue")

    row.due_at = datetime.utcnow()
    user_words.record_event(db, user.id, word, "review_now")
    db.commit()
    return {"word": word, "due_at": iso_utc(row.due_at)}
