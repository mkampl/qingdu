import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.core.rate_limit import limiter
from app.database import SavedText, User, UserWord, get_db
from app.services import cloze
from app.services.migrations import migrate_analysis_data
from app.services.script import convert_analysis_data, to_user_script
from app.services.timestamps import iso_utc

router = APIRouter(tags=["Saved Texts"])
logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[一-鿿]")
# Length of the content snippet in the list payload (the /texts cards show
# ~120 chars; the rest of the text comes from GET /api/texts/{id}).
_PREVIEW_CHARS = 200


def _check_analysis_data(value: object) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("words"), list):
        raise ValueError("analysis_data must be an analysis result with a 'words' list")
    return value


class SaveTextRequest(BaseModel):
    title: str | None = None
    content: str
    analysis_data: dict
    tags: list[str] = []
    glossary_list_ids: list[int] | None = None

    @field_validator("analysis_data")
    @classmethod
    def _valid_analysis(cls, value: dict) -> dict:
        return _check_analysis_data(value)


def _load_analysis(text: SavedText) -> dict | None:
    """The stored analysis blob, or None when the row is damaged (e.g. a
    'null' written by an unvalidated save). Damaged rows are skipped
    instead of failing the whole library."""
    try:
        data = json.loads(text.analysis_data) if text.analysis_data else None
    except (TypeError, ValueError):
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("words"), list):
        logger.warning("saved text %s has unreadable analysis_data; skipping", text.id)
        return None
    return data


def _glossary_ids(text: SavedText) -> list[int] | None:
    try:
        return json.loads(text.glossary_list_ids) if text.glossary_list_ids else None
    except (TypeError, ValueError):
        return None


def _unique_cjk_words(analysis_data: dict) -> set[str]:
    """
    Extract the set of distinct learnable words from an analysed text —
    same definition the SPA uses (must contain CJK; linebreaks excluded).
    """
    out: set[str] = set()
    for w in analysis_data.get("words", []) or []:
        text = w.get("text") or ""
        if not text or text == "\n":
            continue
        if w.get("translation_source") == "linebreak":
            continue
        if not _CJK_RE.search(text):
            continue
        out.add(text)
    return out


def _comprehension(analysis_data: dict, known_set: set[str]) -> dict:
    """
    Per-text comprehension fraction. Counts a word as "comprehensible" if
    the user has marked it known or ignored — both states mean "no lookup
    needed while reading". Ratio uses unique words (not occurrences) so
    repeated words in long texts don't skew the score.
    """
    unique = _unique_cjk_words(analysis_data)
    total = len(unique)
    if total == 0:
        return {"known_unique": 0, "total_unique": 0, "comprehension_score": None}
    known = sum(1 for w in unique if w in known_set)
    return {
        "known_unique": known,
        "total_unique": total,
        "comprehension_score": round(known / total, 4),
    }


def _known_set_for(db: Session, user_id: int) -> set[str]:
    """Single query: the user's full known+ignored word set, as a Python set."""
    rows = (
        db.query(UserWord.word)
        .filter(UserWord.user_id == user_id, UserWord.state.in_(("known", "ignored")))
        .all()
    )
    return {word for (word,) in rows}


def _user_glosses_map(db: Session, user_id: int) -> dict[str, list[dict]]:
    """Phase #120 — every gloss this user has collected, keyed by word.
    Attached to the saved-text payload so the reader's popover surfaces
    the user's curated meanings (dictionary + package tags) even on the
    cached analysis_data path that doesn't re-run /api/analyze."""
    from app.database import UserWordGloss

    rows = (
        db.query(
            UserWord.word,
            UserWordGloss.source,
            UserWordGloss.source_tag,
            UserWordGloss.meaning,
            UserWordGloss.pinyin,
        )
        .join(UserWordGloss, UserWordGloss.user_word_id == UserWord.id)
        .filter(UserWord.user_id == user_id)
        .order_by(UserWord.word, UserWordGloss.created_at)
        .all()
    )
    out: dict[str, list[dict]] = {}
    for word, source, tag, meaning, pinyin in rows:
        out.setdefault(word, []).append(
            {"source": source, "tag": tag, "meaning": meaning, "pinyin": pinyin}
        )
    return out


def _attach_user_glosses(analysis_data: dict, glosses_map: dict[str, list[dict]]) -> None:
    """Walk analysis_data['words'] and attach user_glosses to each word
    that has any glosses in the map. Mutates in place."""
    if not glosses_map or not analysis_data:
        return
    for word in analysis_data.get("words", []) or []:
        text = word.get("text")
        if not text:
            continue
        glosses = glosses_map.get(text)
        if glosses:
            word["user_glosses"] = glosses


@router.post("/api/texts/save")
async def save_text(
    request: Request,
    text_data: SaveTextRequest,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Save analyzed text to database."""
    tags = text_data.tags
    glossary_ids = text_data.glossary_list_ids
    saved_text = SavedText(
        user_id=user.id,
        title=text_data.title,
        content=text_data.content,
        analysis_data=json.dumps(text_data.analysis_data),
        tags=json.dumps(tags) if tags else None,
        glossary_list_ids=json.dumps(glossary_ids) if glossary_ids is not None else None,
    )
    db.add(saved_text)
    db.commit()
    db.refresh(saved_text)
    cloze.forget_misses(user.id)
    return {"id": saved_text.id, "message": "Text saved"}


def _summary(text: SavedText, analysis_data: dict, known_set: set[str], user: User) -> dict:
    """Fields the /texts list and the reader's Today panel need — no
    analysis payload, just a content preview."""
    # Comprehension runs on the canonical (simp) words — known_set is keyed
    # by simp UserWord rows.
    comp = _comprehension(analysis_data, known_set)
    return {
        "id": text.id,
        "title": to_user_script(text.title or "", user),
        "preview": to_user_script((text.content or "")[:_PREVIEW_CHARS], user),
        "date": iso_utc(text.created_at),
        "tags": text.tags,
        "reading_progress": text.reading_progress or 0,
        "share_token": text.share_token,
        "glossary_list_ids": _glossary_ids(text),
        **comp,
    }


@router.get("/api/texts")
def get_texts(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Summaries of the user's saved texts, newest first. The full text
    and analysis come from GET /api/texts/{id} when one is opened."""
    texts = (
        db.query(SavedText)
        .filter(SavedText.user_id == user.id)
        .order_by(SavedText.created_at.desc())
        .all()
    )

    # Pull the user's known/ignored word set once and reuse for every text;
    # the per-text comprehension calc is then pure-Python set intersection.
    known_set = _known_set_for(db, user.id)

    result = []
    for text in texts:
        analysis_data = _load_analysis(text)
        if analysis_data is None:
            continue
        result.append(_summary(text, analysis_data, known_set, user))
    return result


@router.get("/api/texts/{text_id}")
def get_text(
    text_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """One saved text with its content and full analysis, ready for the reader."""
    text = db.query(SavedText).filter(SavedText.id == text_id, SavedText.user_id == user.id).first()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    analysis_data = _load_analysis(text)
    if analysis_data is None:
        raise HTTPException(status_code=422, detail="This saved text's analysis is damaged")

    migrated_data = migrate_analysis_data(analysis_data)
    summary = _summary(text, migrated_data, _known_set_for(db, user.id), user)
    # Phase #120 — attach the user's tagged glosses to each word so
    # the popover shows package + dictionary side by side. Also runs
    # against the canonical (pre-conversion) text since UserWord
    # rows are simp-keyed.
    _attach_user_glosses(migrated_data, _user_glosses_map(db, user.id))
    # Then convert the analysis_data (and the raw `content`) to the
    # user's display script. analysis_data is walked in place: every
    # word.text and grammar sentence.text gets converted.
    convert_analysis_data(migrated_data, user)
    return {
        **summary,
        "content": to_user_script(text.content or "", user),
        "analysisData": migrated_data,
    }


@router.delete("/api/texts/{text_id}")
async def delete_text(
    text_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    text = db.query(SavedText).filter(SavedText.id == text_id, SavedText.user_id == user.id).first()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    db.delete(text)
    db.commit()
    cloze.forget_misses(user.id)
    return {"message": "Text deleted"}


@router.post("/api/texts/{text_id}/share")
async def enable_share(
    text_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Mint (or return the existing) public share token for this saved text.
    The token is a UUID4 — 128 bits of entropy, can't be reasonably
    guessed. Tokens persist until explicitly revoked via DELETE.
    """
    text = db.query(SavedText).filter(SavedText.id == text_id, SavedText.user_id == user.id).first()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    if not text.share_token:
        text.share_token = str(uuid.uuid4())
        db.commit()
        db.refresh(text)
    return {"token": text.share_token}


@router.delete("/api/texts/{text_id}/share")
async def disable_share(
    text_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Revoke the share token. The text remains saved; just no longer
    reachable via /api/share/{token}."""
    text = db.query(SavedText).filter(SavedText.id == text_id, SavedText.user_id == user.id).first()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")
    if text.share_token:
        text.share_token = None
        db.commit()
    return {"message": "Share link revoked"}


@router.get("/api/share/{token}")
@limiter.limit("60/minute")
async def get_shared_text(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public read-only view of a shared text. No auth. Returns only what
    the reader needs to render — no user_id, no progress, no tags.
    Rate-limited to keep the endpoint from being a free analysis cache.
    """
    text = db.query(SavedText).filter(SavedText.share_token == token).first()
    if not text:
        raise HTTPException(status_code=404, detail="Share link not found or revoked")
    analysis_data = json.loads(text.analysis_data) if text.analysis_data else None
    migrated = migrate_analysis_data(analysis_data) if analysis_data else None
    return {
        "title": text.title,
        "content": text.content,
        "analysisData": migrated,
        "created_at": iso_utc(text.created_at),
    }


@router.patch("/api/texts/{text_id}")
async def update_text(
    text_id: int,
    data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Update title/tags/reading_progress/content/analysis_data on a saved text."""
    text = db.query(SavedText).filter(SavedText.id == text_id, SavedText.user_id == user.id).first()
    if not text:
        raise HTTPException(status_code=404, detail="Text not found")

    if "title" in data:
        text.title = data["title"]
    if "tags" in data:
        text.tags = json.dumps(data["tags"]) if data["tags"] else None
    if "reading_progress" in data:
        text.reading_progress = data["reading_progress"]
    if "content" in data:
        text.content = data["content"]
        cloze.forget_misses(user.id)
    if "analysis_data" in data:
        try:
            analysis_data = _check_analysis_data(data["analysis_data"])
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        text.analysis_data = json.dumps(analysis_data)
    if "glossary_list_ids" in data:
        ids = data["glossary_list_ids"]
        text.glossary_list_ids = json.dumps(ids) if ids is not None else None

    db.commit()
    db.refresh(text)
    return {"id": text.id, "title": text.title, "message": "Text updated"}
