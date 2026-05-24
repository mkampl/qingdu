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

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWord, UserWordEvent, get_db
from app.schemas import (
    VALID_WORD_STATES,
    BulkMarkKnownRequest,
    ImportHskRequest,
    WordStateUpdate,
)
from app.services.streak import current_streak, record_activity
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


def _upsert(
    db: Session,
    user_id: int,
    word: str,
    state: str,
    source_text_id: int | None,
) -> UserWord:
    row = db.query(UserWord).filter(UserWord.user_id == user_id, UserWord.word == word).first()
    if row is None:
        row = UserWord(user_id=user_id, word=word, state=state, seen_count=1)
        db.add(row)
    else:
        row.state = state
        row.seen_count = (row.seen_count or 0) + 1
        row.updated_at = datetime.utcnow()
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
    word = payload.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="word is required")

    _upsert(db, user.id, word, payload.state, payload.source_text_id)
    record_activity(user, db)
    db.commit()
    return {"word": word, "state": payload.state}


@router.delete("/api/words/state")
async def clear_word_state(
    word: str,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Reset a word back to 'new' (delete the row). Useful for 'undo'."""
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
        stripped = w.strip()
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
    updated = 0
    for word in words:
        row = existing.get(word)
        if row is None:
            db.add(UserWord(user_id=user.id, word=word, state="known", seen_count=1))
            updated += 1
        elif row.state != "known":
            row.state = "known"
            row.updated_at = datetime.utcnow()
            updated += 1
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
        db.add(UserWord(user_id=user.id, word=word, state="known", seen_count=1))
    # Single event row marking the bulk action — avoids 2 000+ event rows
    # for the typical "mark HSK 1–4" use.
    db.add(
        UserWordEvent(
            user_id=user.id,
            word=f"hsk-{payload.hsk_version}-<=L{payload.up_to_level}",
            event_type="bulk_mark_known",
            new_state="known",
        )
    )
    record_activity(user, db)
    db.commit()
    return {
        "inserted": len(to_insert),
        "skipped": len(existing),
        "total_eligible": len(candidates),
    }
