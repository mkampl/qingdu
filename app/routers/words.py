"""
Per-user word-state tracking — the foundation of LingQ-style "known words"
and the Phase B SRS review loop. Routes here let the SPA read and mutate
each user's word state and read aggregate stats.

State model:
- Absence of a UserWord row == 'new' (never touched).
- A row's `state` column is one of {'learning', 'known', 'ignored'}.
- Clicking a word in the reader bumps 'new' → 'learning' (handled here);
  explicit toggles in the popover write 'known' or 'ignored'.

Every mutation also appends a UserWordEvent so we can power undo and
analytics later without changing this code path.
"""

import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWord, UserWordEvent, UserWordGloss, get_db
from app.schemas import (
    VALID_WORD_STATES,
    BulkMarkKnownRequest,
    ImportHskRequest,
    SnoozeRequest,
    WordStateUpdate,
)
from app.services.due import due_clause, end_of_day, utcnow
from app.services.script import to_canonical, to_user_script
from app.services.srs import ALREADY_KNOWN_STABILITY_DAYS, already_known_state
from app.services.streak import current_streak, record_activity
from app.services.timestamps import iso_utc
from app.services.word_info import lookup_pinyin_meaning
from app.services.word_search import search_clause
from app.state import hsk_vocab

router = APIRouter(tags=["Words"])


def _record_event(
    db: Session,
    user_id: int,
    word: str,
    event_type: str,
    new_state: str | None = None,
    source_text_id: int | None = None,
) -> None:
    db.add(
        UserWordEvent(
            user_id=user_id,
            word=word,
            event_type=event_type,
            new_state=new_state,
            source_text_id=source_text_id,
        )
    )


def _apply_known_scheduling(row: UserWord) -> None:
    """Schedule a row as "already known" — Review-phase FSRS card with
    ~90d stability and a randomised first-review date in (60d, 180d).
    State stays 'known' so the reader colours it accordingly; the review
    queue now includes both 'learning' and 'known' so it still rotates."""
    seeded = already_known_state()
    row.state = "known"
    row.fsrs_state = seeded["fsrs_state"]
    row.stability = seeded["stability"]
    row.difficulty = seeded["difficulty"]
    row.due_at = seeded["due_at"]
    row.last_reviewed_at = seeded["last_reviewed_at"]


def _resolve_snapshot(
    word: str,
    pkg_meaning: str | None,
    pkg_pinyin: str | None,
    pkg_translation_source: str | None,
) -> tuple[str, str, str | None]:
    """Decide which (pinyin, meaning, meaning_source) to stamp on a row.

    When the caller hands us a package-sourced snapshot
    (`translation_source == "package"` plus an actual meaning), we use it
    verbatim and tag the row "package" so subsequent dictionary clicks
    don't overwrite it. Otherwise we fall through to the in-process
    dictionary chain — same behaviour as before this column existed.
    """
    if pkg_translation_source == "package" and (pkg_meaning or pkg_pinyin):
        return (pkg_pinyin or "", pkg_meaning or "", "package")
    pinyin, meaning = lookup_pinyin_meaning(word)
    return pinyin, meaning, "dictionary"


def _ensure_gloss(
    db: Session,
    row: UserWord,
    *,
    pinyin: str | None,
    meaning: str | None,
    source: str,
    source_tag: str | None,
) -> None:
    """Phase #120 — add a gloss to a UserWord row if no equivalent one
    exists yet. Equivalence: same (source, source_tag) pair.

    The first dictionary gloss added is the row's primary meaning. The
    legacy `meaning`/`pinyin` columns on UserWord still get populated
    with the *first* gloss we see (so existing read paths keep working
    until they're migrated); subsequent glosses go to UserWordGloss
    only.
    """
    if not meaning:
        return
    existing = next(
        (
            g
            for g in row.glosses
            if g.source == source and (g.source_tag or None) == (source_tag or None)
        ),
        None,
    )
    if existing is not None:
        # Refresh the meaning if the dictionary's view of this word
        # drifted (e.g. CC-CEDICT picked a better primary after a
        # heuristic tune). Package glosses are immutable.
        if source == "dictionary":
            if meaning and meaning != existing.meaning:
                existing.meaning = meaning
            if pinyin and pinyin != existing.pinyin:
                existing.pinyin = pinyin
        return
    db.add(
        UserWordGloss(
            user_word=row,
            pinyin=pinyin or None,
            meaning=meaning,
            source=source,
            source_tag=source_tag,
        )
    )
    # Mirror the first gloss into the legacy columns so callers that
    # haven't been migrated yet still see *something* on the row. The
    # gloss list itself is the source of truth.
    if not row.meaning:
        row.meaning = meaning
        row.pinyin = pinyin or None
        row.meaning_source = source


def _upsert(
    db: Session,
    user_id: int,
    word: str,
    state: str,
    source_text_id: int | None,
    pkg_meaning: str | None = None,
    pkg_pinyin: str | None = None,
    pkg_translation_source: str | None = None,
    pkg_source_tag: str | None = None,
) -> UserWord:
    is_pkg = pkg_translation_source == "package" and (pkg_meaning or pkg_pinyin) is not None

    row = db.query(UserWord).filter(UserWord.user_id == user_id, UserWord.word == word).first()
    if row is None:
        row = UserWord(
            user_id=user_id,
            word=word,
            state=state,
            seen_count=1,
        )
        if state == "known":
            _apply_known_scheduling(row)
        db.add(row)
        db.flush()  # row.id needed for gloss FK
    else:
        # Same guard as bulk_mark_known: a mature card (stability already
        # past the "known" seed) keeps its FSRS history instead of being
        # reseeded to 90 days.
        if state == "known" and (row.stability or 0) < ALREADY_KNOWN_STABILITY_DAYS:
            _apply_known_scheduling(row)
        else:
            row.state = state
        row.seen_count = (row.seen_count or 0) + 1
        row.updated_at = datetime.utcnow()

    # Always ensure a dictionary gloss exists — that's the default
    # learner-facing meaning regardless of which context they clicked
    # the word in. lookup_pinyin_meaning hits HSK/CC-CEDICT/compound/pypinyin.
    dict_pinyin, dict_meaning = lookup_pinyin_meaning(word)
    if dict_meaning:
        _ensure_gloss(
            db,
            row,
            pinyin=dict_pinyin,
            meaning=dict_meaning,
            source="dictionary",
            source_tag=None,
        )

    # Add the package gloss as its own row if the click came from a
    # package. Multiple packages can co-exist as separate glosses
    # tagged by package name.
    if is_pkg:
        _ensure_gloss(
            db,
            row,
            pinyin=pkg_pinyin,
            meaning=pkg_meaning,
            source="package",
            source_tag=pkg_source_tag or "package",
        )

    _record_event(db, user_id, word, "state_change", state, source_text_id)
    return row


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

    row = _upsert(
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
        _record_event(db, user.id, word, "state_change", None, None)
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
    no-ops; words in other states are overwritten.
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
        return {"updated": 0, "total": 0}

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
    for word in words:
        snap = snapshots.get(word)
        pkg_meaning = snap.meaning if snap else None
        pkg_pinyin = snap.pinyin if snap else None
        pkg_source = snap.translation_source if snap else None
        pkg_tag = snap.package_source if snap else None
        is_pkg = pkg_source == "package" and (pkg_meaning or pkg_pinyin) is not None

        row = existing.get(word)
        if row is None:
            row = UserWord(user_id=user.id, word=word, state="learning", seen_count=1)
            _apply_known_scheduling(row)
            db.add(row)
            db.flush()
            updated += 1
        elif (row.stability or 0) < ALREADY_KNOWN_STABILITY_DAYS:
            _apply_known_scheduling(row)
            row.updated_at = datetime.utcnow()
            updated += 1

        # Phase #120 — same gloss logic as _upsert(): always seed a
        # dictionary gloss, plus a tagged package gloss when relevant.
        dict_pinyin, dict_meaning = lookup_pinyin_meaning(word)
        if dict_meaning:
            _ensure_gloss(
                db,
                row,
                pinyin=dict_pinyin,
                meaning=dict_meaning,
                source="dictionary",
                source_tag=None,
            )
        if is_pkg:
            _ensure_gloss(
                db,
                row,
                pinyin=pkg_pinyin,
                meaning=pkg_meaning,
                source="package",
                source_tag=pkg_tag or "package",
            )
        _record_event(db, user.id, word, "bulk_mark_known", "known", payload.source_text_id)
    record_activity(user, db)
    db.commit()
    return {"updated": updated, "total": len(words)}


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


def _hsk_words_at_or_below(up_to_level: int, hsk_version: str) -> list[str]:
    """
    Return the list of HSK words at level <= `up_to_level` for the chosen
    version. Single-character entries are included; that's intentional —
    they're how learners build pinyin / radical recognition even before
    they read the compounds.
    """
    field = "level_new" if hsk_version == "new" else "level_old"
    prefix = "new-" if hsk_version == "new" else "old-"
    words: list[str] = []
    for word, entry in hsk_vocab.items():
        level = entry.get(field)
        if not level or not level.startswith(prefix):
            continue
        raw = level[len(prefix) :].replace("+", "")
        try:
            n = int(raw)
        except ValueError:
            continue
        if n <= up_to_level:
            words.append(word)
    return words


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

    candidates = _hsk_words_at_or_below(payload.up_to_level, payload.hsk_version)
    if not candidates:
        return {"inserted": 0, "skipped": 0, "total_eligible": 0}

    # Find which candidates the user has already touched.
    existing_rows = (
        db.query(UserWord.word)
        .filter(UserWord.user_id == user.id, UserWord.word.in_(candidates))
        .all()
    )
    existing = {w for (w,) in existing_rows}

    to_insert = [w for w in candidates if w not in existing]
    for word in to_insert:
        pinyin, meaning = lookup_pinyin_meaning(word)
        row = UserWord(
            user_id=user.id,
            word=word,
            state="learning",
            seen_count=1,
            pinyin=pinyin or None,
            meaning=meaning or None,
            meaning_source="dictionary",
        )
        _apply_known_scheduling(row)
        db.add(row)
    # Single event row marking the bulk action — avoids 2 000+ event rows
    # for the typical "mark HSK 1–4" use.
    db.add(
        UserWordEvent(
            user_id=user.id,
            word=f"hsk-{payload.hsk_version}-<=L{payload.up_to_level}",
            event_type="bulk_mark_known",
            new_state="known",
            word_count=len(to_insert),
        )
    )
    record_activity(user, db)
    db.commit()
    return {
        "inserted": len(to_insert),
        "skipped": len(existing),
        "total_eligible": len(candidates),
    }


def _hsk_level_number(level: str | None) -> int | None:
    """ "new-3" -> 3, "old-6" -> 6, "new-7-9" -> 7; None for anything else."""
    if not level:
        return None
    m = re.match(r"^(?:new|old)-(\d+)", level)
    return int(m.group(1)) if m else None


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
    lvl = _hsk_level_number(entry.get(first))
    if lvl is None:
        lvl = _hsk_level_number(entry.get(second))
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
        q = q.filter(due_clause(end_of_day(now, due_within_days)))

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
    """Push due_at forward by `days` days.

    Body: {word: str, days: int 1..365}. Default 3 if unset; anything else
    is a 422.
    Useful when the user isn't ready to re-encounter a word yet but doesn't
    want to mark it 'known' or remove it from the queue entirely.
    """
    from datetime import timedelta

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
    _record_event(db, user.id, word, "snooze")
    db.commit()
    return {"word": word, "days": days, **_schedule_fields(row, now)}


@router.post("/api/words/review-now")
async def review_now(
    payload: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Set due_at = now so the word surfaces immediately in /review."""
    from datetime import datetime

    word_raw = (payload.get("word") or "").strip()
    if not word_raw:
        raise HTTPException(400, "word is required")
    word = to_canonical(word_raw, user)
    row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word).first()
    if row is None:
        raise HTTPException(404, "word not in your queue")

    row.due_at = datetime.utcnow()
    _record_event(db, user.id, word, "review_now")
    db.commit()
    return {"word": word, "due_at": iso_utc(row.due_at)}
