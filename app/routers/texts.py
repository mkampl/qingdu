import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.auth import require_auth
from app.core.rate_limit import limiter
from app.database import SavedText, User, UserWord, get_db
from app.services.migrations import migrate_analysis_data

router = APIRouter(tags=["Saved Texts"])

_CJK_RE = re.compile(r"[一-鿿]")


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


@router.post("/api/texts/save")
async def save_text(
    request: Request,
    text_data: dict,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Save analyzed text to database."""
    tags = text_data.get("tags", [])
    saved_text = SavedText(
        user_id=user.id,
        title=text_data.get("title"),
        content=text_data.get("content"),
        analysis_data=json.dumps(text_data.get("analysis_data")),
        tags=json.dumps(tags) if tags else None,
    )
    db.add(saved_text)
    db.commit()
    db.refresh(saved_text)
    return {"id": saved_text.id, "message": "Text saved"}


@router.get("/api/texts")
async def get_texts(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Return all saved texts for the current user, eager-loading the relation."""
    texts = (
        db.query(SavedText)
        .options(joinedload(SavedText.user))
        .filter(SavedText.user_id == user.id)
        .order_by(SavedText.created_at.desc())
        .all()
    )

    # Pull the user's known/ignored word set once and reuse for every text;
    # the per-text comprehension calc is then pure-Python set intersection.
    known_set = _known_set_for(db, user.id)

    result = []
    for text in texts:
        analysis_data = json.loads(text.analysis_data)
        migrated_data = migrate_analysis_data(analysis_data)
        comp = _comprehension(migrated_data, known_set)
        result.append(
            {
                "id": text.id,
                "title": text.title,
                "content": text.content,
                "date": text.created_at.isoformat(),
                "analysisData": migrated_data,
                "tags": text.tags,
                "reading_progress": text.reading_progress or 0,
                "share_token": text.share_token,
                **comp,
            }
        )
    return result


@router.delete("/api/texts/{text_id}")
async def delete_text(
    text_id: int,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    text = db.query(SavedText).filter(SavedText.id == text_id, SavedText.user_id == user.id).first()
    if text:
        db.delete(text)
        db.commit()
        return {"message": "Text deleted"}
    return {"error": "Text not found"}


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
        "created_at": text.created_at.isoformat(),
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
    if "analysis_data" in data:
        text.analysis_data = json.dumps(data["analysis_data"])

    db.commit()
    db.refresh(text)
    return {"id": text.id, "title": text.title, "message": "Text updated"}
