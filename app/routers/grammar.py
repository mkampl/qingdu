"""The grammar section: points of the grammar catalog the user has met in
what they read, the sentences that show them, and practice
(services/grammar_book). Point ids are catalog ids ("hsk30-021"); the
reader's regex pattern ids ("ba") are accepted too."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, get_db
from app.services import grammar_book
from app.services.streak import record_activity

router = APIRouter(tags=["Grammar"])


class PracticeResult(BaseModel):
    correct: int = Field(..., ge=0, le=100)
    total: int = Field(..., ge=1, le=100)


@router.get("/api/grammar")
def grammar_overview(user: User = Depends(require_auth), db: Session = Depends(get_db)) -> dict:
    """Every catalog point with how often the user met it in texts they
    read to the end, and their practice state. Also queues the user's
    sentences for the LLM, when there is one."""
    return grammar_book.overview(db, user.id)


@router.get("/api/grammar/{pattern_id}")
def grammar_pattern(
    pattern_id: str, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    detail = grammar_book.point_detail(db, user.id, pattern_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Unknown grammar point")
    return detail


@router.get("/api/grammar/{pattern_id}/practice")
def grammar_practice(
    pattern_id: str, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    """Gap and word-order exercises, from the user's own sentences first."""
    body = grammar_book.practice(db, user.id, pattern_id)
    if not body.get("items"):
        raise HTTPException(status_code=404, detail="Nothing to practise for this pattern")
    return body


@router.post("/api/grammar/{pattern_id}/practice")
def grammar_practice_done(
    pattern_id: str,
    result: PracticeResult,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Store a practice round; it counts for the streak like a review."""
    if grammar_book.point_detail(db, user.id, pattern_id) is None:
        raise HTTPException(status_code=404, detail="Unknown grammar point")
    record_activity(user, db)
    return grammar_book.record(
        db, user.id, pattern_id, min(result.correct, result.total), result.total
    )
