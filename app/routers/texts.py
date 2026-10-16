import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.core.rate_limit import limiter
from app.database import SavedText, User, UserWord, get_db
from app.services import cloze, dict_data, readability
from app.services.gloss_refresh import DICT_VERSION_KEY, refresh_analysis
from app.services.migrations import migrate_analysis_data
from app.services.script import convert_analysis_data, to_user_script
from app.services.timestamps import iso_utc

router = APIRouter(tags=["Saved Texts"])
logger = logging.getLogger(__name__)

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


def _refreshed_analysis(db: Session, text: SavedText) -> dict | None:
    """The stored analysis with its dictionary and MT glosses brought up to
    the current dictionary. The refreshed blob is written back (with the
    version it was resolved against), so this only does work on the first
    open after a dictionary change."""
    analysis_data = _load_analysis(text)
    if analysis_data is not None and refresh_analysis(analysis_data, dict_data.dict_version()):
        text.analysis_data = json.dumps(analysis_data)
        db.commit()
    return analysis_data


def _strip_dict_version(analysis_data: dict) -> dict:
    """A client-supplied analysis is resolved against whatever dictionary
    the server has now, never against a version the client claims."""
    analysis_data.pop(DICT_VERSION_KEY, None)
    return analysis_data


def _glossary_ids(text: SavedText) -> list[int] | None:
    try:
        return json.loads(text.glossary_list_ids) if text.glossary_list_ids else None
    except (TypeError, ValueError):
        return None


def _comprehension(analysis_data: dict, status: dict[str, str]) -> dict:
    """How readable a saved text is for the user — the same count the
    reader shows (services/readability): the share of running words known,
    and how many missing words would make it readable. `known_unique` and
    `total_unique` count distinct words for the tooltip."""
    words = analysis_data.get("words", []) or []
    tokens = [w.get("text") or "" for w in words]
    extra = {
        w.get("text")
        for w in words
        if w.get("translation_source") in ("package", "glossary") and w.get("text")
    }
    summary = readability.summarize(readability.count_words(tokens, extra=extra), status)
    if summary.total == 0:
        return {
            "known_unique": 0,
            "total_unique": 0,
            "comprehension_score": None,
            "to_unlock": 0,
            "unlocked": False,
        }
    return {
        "known_unique": summary.unique - len(summary.missing) - len(summary.in_progress_words),
        "total_unique": summary.unique,
        "comprehension_score": round(summary.known_pct, 4),
        "to_unlock": summary.to_unlock,
        "unlocked": summary.unlocked,
    }


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
        analysis_data=json.dumps(_strip_dict_version(text_data.analysis_data)),
        tags=json.dumps(tags) if tags else None,
        glossary_list_ids=json.dumps(glossary_ids) if glossary_ids is not None else None,
    )
    db.add(saved_text)
    db.commit()
    db.refresh(saved_text)
    cloze.forget_misses(user.id)
    return {"id": saved_text.id, "message": "Text saved"}


def _summary(text: SavedText, analysis_data: dict, status: dict[str, str], user: User) -> dict:
    """Fields the /texts list and the reader's Today panel need — no
    analysis payload, just a content preview."""
    # Comprehension runs on the canonical (simp) words — the status map is
    # keyed by simp UserWord rows.
    comp = _comprehension(analysis_data, status)
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

    # Pull the user's word status once and reuse it for every text.
    status = readability.user_status(db, user.id)

    result = []
    for text in texts:
        analysis_data = _load_analysis(text)
        if analysis_data is None:
            continue
        result.append(_summary(text, analysis_data, status, user))
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
    analysis_data = _refreshed_analysis(db, text)
    if analysis_data is None:
        raise HTTPException(status_code=422, detail="This saved text's analysis is damaged")

    migrated_data = migrate_analysis_data(analysis_data)
    summary = _summary(text, migrated_data, readability.user_status(db, user.id), user)
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
    analysis_data = _refreshed_analysis(db, text)
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
        text.analysis_data = json.dumps(_strip_dict_version(analysis_data))
    if "glossary_list_ids" in data:
        ids = data["glossary_list_ids"]
        text.glossary_list_ids = json.dumps(ids) if ids is not None else None

    db.commit()
    db.refresh(text)
    return {"id": text.id, "title": text.title, "message": "Text updated"}
