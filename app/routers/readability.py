"""How readable a text is for the signed-in user ("make this text readable").

The reader posts the tokens of the text it shows; the response says what
share of the running words the user knows, how much more counts once the
words in review are learned, and which words are still missing. See
services/readability for the counting rules.

Pre-learning takes missing words of a text into review: each becomes a
learning word with the sentence it stands in as its context sentence (and
the text's own meaning when a package or glossary gives one), and is
linked to the text so the reader can show the progress and a review
session can focus on that text.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import TextWord, User, UserWord, get_db
from app.routers.words import _context_title, _ensure_gloss, _upsert, may_create_word
from app.services import cloze, readability
from app.services.script import to_canonical, to_user_script
from app.services.streak import record_activity

router = APIRouter(tags=["Readability"])

TextKey = Field(None, max_length=200, pattern=r"^(saved|library|text):[\w.\-]+$")


class ReadabilityRequest(BaseModel):
    # The text's tokens in reading order, as the analysis split them.
    tokens: list[str] = Field(default_factory=list, max_length=60000)
    # Words with a meaning of their own in this text (package or glossary
    # terms) that count as words although no dictionary has them.
    extra: list[str] = Field(default_factory=list, max_length=5000)
    # Names the text for the pre-learned progress: "saved:<id>",
    # "library:<slug>" or "text:<hash>".
    text_key: str | None = TextKey


class TextGloss(BaseModel):
    """The text's own meaning for a word."""

    meaning: str = Field(..., min_length=1, max_length=500)
    pinyin: str | None = Field(None, max_length=128)
    # 'package' (pre-analysed package) or 'glossary' (a vocab list used as
    # glossary); the tag is the package or list name.
    source: str = Field(..., pattern=r"^(package|glossary)$")
    # Kept whole: the reader's popover stores a package's full source name
    # as the tag, and the review matches the text's meaning by it.
    tag: str | None = Field(None, max_length=500)


class PrelearnRequest(ReadabilityRequest):
    words: list[str] = Field(..., min_length=1, max_length=500)
    text_key: str = Field(..., max_length=200, pattern=r"^(saved|library|text):[\w.\-]+$")
    title: str | None = Field(None, max_length=160)
    source_text_id: int | None = None
    library_slug: str | None = Field(None, max_length=120)
    glosses: dict[str, TextGloss] = Field(default_factory=dict, max_length=500)


def _stored_source(gloss: TextGloss | None) -> str | None:
    """The user_word_glosses source a text gloss is stored under."""
    if gloss is None:
        return None
    return "package" if gloss.source == "package" else "list"


def _prelearned(db: Session, user: User, text_key: str | None) -> dict | None:
    """How many words were pre-learned for this text and how many of them
    count as known by now."""
    if not text_key:
        return None
    rows = (
        db.query(UserWord.state, UserWord.stability)
        .join(TextWord, (TextWord.word == UserWord.word) & (TextWord.user_id == UserWord.user_id))
        .filter(TextWord.user_id == user.id, TextWord.text_key == text_key)
        .all()
    )
    learned = sum(
        1 for state, stability in rows if readability.classify(state, stability) == "known"
    )
    return {"total": len(rows), "learned": learned}


def summary_payload(summary: readability.Summary, user: User) -> dict:
    return {
        "threshold": summary.threshold,
        "total": summary.total,
        "unique": summary.unique,
        "known": summary.known,
        "in_progress": summary.in_progress,
        "known_pct": round(summary.known_pct, 4),
        "with_progress_pct": round(summary.with_progress_pct, 4),
        "to_unlock": summary.to_unlock,
        "unlocked": summary.unlocked,
        "missing_count": len(summary.missing),
        "missing": [
            {**readability.missing_payload(w, c), "word": to_user_script(w, user)}
            for w, c in summary.missing[: readability.MAX_MISSING_LISTED]
        ],
        "in_progress_words": [to_user_script(w, user) for w in summary.in_progress_words],
    }


def _summary(db: Session, user: User, payload: ReadabilityRequest) -> dict:
    tokens = [to_canonical(t, user) for t in payload.tokens]
    extra = {to_canonical(w.strip(), user) for w in payload.extra if w.strip()}
    summary = readability.for_user(db, user.id, tokens, extra=extra)
    return {
        **summary_payload(summary, user),
        "prelearned": _prelearned(db, user, payload.text_key),
    }


@router.post("/api/readability")
def text_readability(
    payload: ReadabilityRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Readability of the posted tokens for the signed-in user."""
    return _summary(db, user, payload)


@router.post("/api/readability/prelearn")
def prelearn_words(
    payload: PrelearnRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Take the chosen words of a text into review and link them to it.

    Words the user already has keep their state (a known word is not sent
    back to learning); they are still linked to the text. Phrases that are
    not dictionary words are skipped. Returns the text's new readability.
    """
    tokens = [to_canonical(t, user) for t in payload.tokens]
    split = readability.sentences(tokens)
    extra = {to_canonical(w.strip(), user) for w in payload.extra if w.strip()}
    glosses = {to_canonical(w, user): g for w, g in payload.glosses.items()}
    title = (payload.title or "").strip()[:160] or _context_title(
        db, user.id, payload.source_text_id, payload.library_slug
    )
    linked = {
        w
        for (w,) in db.query(TextWord.word).filter(
            TextWord.user_id == user.id, TextWord.text_key == payload.text_key
        )
    }

    added: list[str] = []
    skipped: list[str] = []
    for raw in dict.fromkeys(payload.words):
        word = to_canonical(raw.strip(), user)
        if not word:
            continue
        gloss = glosses.get(word)
        is_pkg = gloss is not None and gloss.source == "package"
        if not may_create_word(db, user.id, word, is_pkg=is_pkg or word in extra):
            skipped.append(to_user_script(word, user))
            continue
        row = db.query(UserWord).filter(UserWord.user_id == user.id, UserWord.word == word).first()
        if row is None:
            row = _upsert(
                db,
                user.id,
                word,
                "learning",
                payload.source_text_id,
                pkg_meaning=gloss.meaning if is_pkg else None,
                pkg_pinyin=gloss.pinyin if is_pkg else None,
                pkg_translation_source="package" if is_pkg else None,
                pkg_source_tag=gloss.tag if is_pkg else None,
            )
            added.append(to_user_script(word, user))
        if gloss is not None and gloss.source == "glossary":
            # A vocab list's own meaning, stored like "learn this list" does.
            _ensure_gloss(
                db,
                row,
                pinyin=gloss.pinyin,
                meaning=gloss.meaning,
                source="list",
                source_tag=gloss.tag or "list",
            )
        cloze.adopt_sentence(row, readability.sentence_for(split, word), title)
        if word not in linked:
            db.add(
                TextWord(
                    user_id=user.id,
                    text_key=payload.text_key,
                    word=word,
                    title=title,
                    gloss_source=_stored_source(gloss),
                    gloss_tag=(gloss.tag or _stored_source(gloss)) if gloss else None,
                )
            )
            linked.add(word)
    if added:
        record_activity(user, db)
    db.commit()
    return {"added": added, "skipped": skipped, **_summary(db, user, payload)}
