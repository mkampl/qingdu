"""Bundled HSK library endpoints.

- `GET /api/library` — manifest of all bundled texts (metadata only)
- `GET /api/library/{slug}` — full pre-analyzed text
- `GET /api/library/for-you` — auth, filtered by the user's known-word set
  into the LingQ-style 85-98% comprehension band
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserWord, get_db
from app.services import library

router = APIRouter(tags=["Library"])


@router.get("/api/library")
def list_library() -> dict:
    """All library texts, metadata only. Cheap to call; cacheable client-side."""
    return {"items": library.manifest()}


@router.get("/api/library/for-you")
def for_you(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
    min_score: float = Query(0.85, ge=0.0, le=1.0),
    max_score: float = Query(0.98, ge=0.0, le=1.0),
    limit: int = Query(12, ge=1, le=50),
) -> dict:
    """Library entries inside the user's comprehension zone.

    Empty list (rather than 404) when the user has no known-word data yet —
    the frontend hides the rail in that case without erroring.
    """
    known = {
        w
        for (w,) in db.query(UserWord.word)
        .filter(UserWord.user_id == user.id, UserWord.state.in_(("known", "ignored")))
        .all()
    }
    if not known:
        return {"items": [], "reason": "no_known_words"}

    items = library.for_user(
        known,
        min_score=min_score,
        max_score=max_score,
        limit=limit,
    )
    return {"items": items}


@router.get("/api/library/{slug}")
def get_one(slug: str) -> dict:
    entry = library.get(slug)
    if entry is None:
        raise HTTPException(404, "library entry not found")
    return entry
