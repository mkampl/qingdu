"""Placement test for new learners (services/placement)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import User, get_db
from app.services import placement, user_words

router = APIRouter(tags=["Placement"])


class PlacementResult(BaseModel):
    # Highest level passed; 0 = beginner (nothing is marked known).
    level: int = Field(..., ge=0, le=7)


@router.get("/api/placement/items")
def placement_items(
    level: int = Query(..., ge=1, le=7),
    n: int = Query(6, ge=1, le=placement.MAX_ITEMS),
    exclude: str = Query("", max_length=2000),
    user: User = Depends(require_auth),
) -> dict:
    """Questions for one round: the meaning of `n` words of the level."""
    _ = user
    out = placement.items(level, n, {w for w in exclude.split(",") if w})
    if not out:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")
    return {"items": out}


@router.post("/api/placement/finish")
async def placement_finish(
    result: PlacementResult,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Mark the words of the passed levels as known (HSK 7 = 7-9)."""
    if result.level == 0:
        return {"inserted": 0, "skipped": 0, "total_eligible": 0}
    up_to = 9 if result.level == 7 else result.level
    return user_words.import_hsk_known(db, user, up_to, "new")
