"""Bundled HSK library endpoints.

- `GET /api/library` — manifest of all bundled texts (metadata only)
- `GET /api/library/{slug}` — full pre-analyzed text
- `GET /api/library/for-you` — auth, filtered by the user's known-word set
  into the LingQ-style 85-98% comprehension band
- `GET /api/library/progress` — auth, the caller's completion state for
  every started text
- `POST/DELETE /api/library/{slug}/read` — self-reported "I read this"
- `GET /api/library/{slug}/quiz` — the text's comprehension questions,
  answer key stripped
- `POST /api/library/{slug}/quiz` — grade submitted answers; an all-correct
  submission records completion (stronger than a manual mark-as-read)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, UserLibraryProgress, UserWord, get_db
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


class QuizSubmission(BaseModel):
    answers: list[int]


def _progress_dict(row: UserLibraryProgress) -> dict:
    return {
        "status": row.status,
        "score": row.score,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


@router.get("/api/library/progress")
def get_progress(
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """The caller's completion state for every library text they've touched,
    keyed by slug. Absence of a key means not started."""
    rows = db.query(UserLibraryProgress).filter(UserLibraryProgress.user_id == user.id).all()
    return {"items": {r.slug: _progress_dict(r) for r in rows}}


@router.post("/api/library/{slug}/read")
def mark_read(
    slug: str,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Self-reported completion. Never downgrades an existing quiz pass."""
    if library.get(slug) is None:
        raise HTTPException(404, "library entry not found")
    row = (
        db.query(UserLibraryProgress)
        .filter(UserLibraryProgress.user_id == user.id, UserLibraryProgress.slug == slug)
        .first()
    )
    if row is None:
        row = UserLibraryProgress(user_id=user.id, slug=slug, status="read")
        db.add(row)
    elif row.status != "quiz":
        row.status = "read"
        row.completed_at = datetime.utcnow()
    db.commit()
    return _progress_dict(row)


@router.delete("/api/library/{slug}/read")
def unmark_read(
    slug: str,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Reset progress for a text (undo a mis-click or retake a quiz)."""
    db.query(UserLibraryProgress).filter(
        UserLibraryProgress.user_id == user.id, UserLibraryProgress.slug == slug
    ).delete()
    db.commit()
    return {"status": None}


@router.get("/api/library/{slug}/quiz")
def get_quiz(slug: str, user: User = Depends(require_auth)) -> dict:
    qs = library.quiz_questions(slug)
    if qs is None:
        raise HTTPException(404, "no quiz for this text")
    return {"questions": qs}


@router.post("/api/library/{slug}/quiz")
def submit_quiz(
    slug: str,
    body: QuizSubmission,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    qs = library.questions(slug)
    if qs is None:
        raise HTTPException(404, "no quiz for this text")
    if len(body.answers) != len(qs):
        raise HTTPException(400, "expected an answer for every question")

    results = [a == q["answer_index"] for a, q in zip(body.answers, qs, strict=True)]
    all_correct = all(results)

    row = (
        db.query(UserLibraryProgress)
        .filter(UserLibraryProgress.user_id == user.id, UserLibraryProgress.slug == slug)
        .first()
    )
    if all_correct:
        if row is None:
            row = UserLibraryProgress(user_id=user.id, slug=slug, status="quiz", score=len(qs))
            db.add(row)
        else:
            row.status = "quiz"
            row.score = len(qs)
            row.completed_at = datetime.utcnow()
        db.commit()

    return {
        "results": results,
        "all_correct": all_correct,
        "progress": _progress_dict(row) if row else None,
    }


@router.get("/api/library/{slug}")
def get_one(slug: str) -> dict:
    entry = library.get(slug)
    if entry is None:
        raise HTTPException(404, "library entry not found")
    return entry
