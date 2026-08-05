"""
Read/write API for external integrations — token-scoped (see
app/routers/tokens.py), separate from the SPA's own /api/words/* routes.

Built for the language-speaking-companion use case: an outside app (its
own whisper/LLM/TTS stack) reads which words a user already knows, and
reports newly-encountered vocabulary back so it lands in the same review
pipeline a reader click would create.

Kept deliberately narrow: read:words and write:words only ever touch
UserWord rows. No access to auth, admin, streak/freeze counters (those
stay server-derived via record_activity), or any other account data.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_api_scope
from app.database import User, UserWord, get_db
from app.routers.words import _upsert
from app.services.script import to_canonical
from app.services.streak import record_activity
from app.state import hsk_vocab

router = APIRouter(prefix="/api/external", tags=["External API"])


class EncounteredWord(BaseModel):
    word: str
    # Free-text, purely informational (shows up nowhere yet but kept for
    # future analytics / provenance without another migration).
    source: str = Field(default="external", max_length=64)


class EncounteredWordsRequest(BaseModel):
    words: list[EncounteredWord]


def _hsk_level(word: str) -> str | None:
    entry = hsk_vocab.get(word)
    if not entry:
        return None
    return entry.get("level_new") or entry.get("level_old")


@router.get("/words")
async def list_known_words(
    state: str | None = None,
    user: User = Depends(require_api_scope("read:words")),
    db: Session = Depends(get_db),
) -> dict:
    """Return the caller's word states. `state` optionally filters to one
    of learning/known/ignored; omitted returns everything the user has
    touched (absence of a row means 'new' and is never listed here)."""
    query = db.query(UserWord).filter(UserWord.user_id == user.id)
    if state:
        query = query.filter(UserWord.state == state)
    rows = query.all()
    return {
        "words": [
            {
                "word": row.word,
                "state": row.state,
                "pinyin": row.pinyin,
                "meaning": row.meaning,
                "hsk_level": _hsk_level(row.word),
            }
            for row in rows
        ]
    }


@router.post("/words/encountered")
async def report_encountered_words(
    payload: EncounteredWordsRequest,
    user: User = Depends(require_api_scope("write:words")),
    db: Session = Depends(get_db),
) -> dict:
    """Upsert newly-encountered words as 'learning' — the same state a
    reader click assigns. A word the user already marked 'known' or
    'ignored' is left untouched; this only ever moves a word toward
    tracked, never overrides an explicit prior choice."""
    accepted = []
    for item in payload.words:
        word = to_canonical(item.word.strip(), user)
        if not word:
            continue
        existing = (
            db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word).first()
        )
        if existing and existing.state in ("known", "ignored"):
            continue
        _upsert(db, user.id, word, "learning", None)
        accepted.append(word)

    if accepted:
        record_activity(user, db)
    db.commit()
    return {"accepted": accepted}
