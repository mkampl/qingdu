"""Topic series: texts written by the LLM on one topic (services/text_series)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import TextSeries, User, get_db
from app.services import llm, text_series

router = APIRouter(tags=["Topic series"])

Length = Literal["short", "medium", "long"]


class SeriesCreate(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    level: int = Field(3, ge=1, le=7)
    new_words: int = Field(10, ge=text_series.MIN_NEW, le=text_series.MAX_NEW)
    length: Length = "medium"


class SeriesUpdate(BaseModel):
    level: int | None = Field(None, ge=1, le=7)
    new_words: int | None = Field(None, ge=text_series.MIN_NEW, le=text_series.MAX_NEW)
    length: Length | None = None


def _owned(db: Session, user: User, series_id: int) -> TextSeries:
    series = (
        db.query(TextSeries)
        .filter(TextSeries.id == series_id, TextSeries.user_id == user.id)
        .first()
    )
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


@router.get("/api/series")
def list_series(user: User = Depends(require_auth), db: Session = Depends(get_db)) -> list:
    rows = db.query(TextSeries).filter(TextSeries.user_id == user.id).all()
    return [text_series.payload(db, s) for s in rows]


@router.get("/api/series/{series_id}")
def get_series(
    series_id: int, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    return text_series.payload(db, _owned(db, user, series_id))


@router.post("/api/series")
async def create_series(
    body: SeriesCreate, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    """A new series with its folder; the first text is written right away."""
    llm.require(text_series.FEATURE)
    llm.charge(db, user.id)
    series = text_series.create(
        db, user, body.topic.strip(), body.level, body.new_words, body.length
    )
    text_series.start(db, series)
    return text_series.payload(db, series)


@router.patch("/api/series/{series_id}")
def update_series(
    series_id: int,
    body: SeriesUpdate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Change the level, new words per text or length of the next texts."""
    series = _owned(db, user, series_id)
    for field in ("level", "new_words", "length"):
        value = getattr(body, field)
        if value is not None:
            setattr(series, field, value)
    db.commit()
    return text_series.payload(db, series)


@router.post("/api/series/{series_id}/next")
async def next_text(
    series_id: int, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    """Write the next text of the series in the background; poll GET."""
    series = _owned(db, user, series_id)
    llm.require(text_series.FEATURE)
    if text_series.payload(db, series)["generating"]:
        return text_series.payload(db, series)
    llm.charge(db, user.id)
    text_series.start(db, series)
    return text_series.payload(db, series)
