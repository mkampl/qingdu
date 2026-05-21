import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.auth import require_auth
from app.database import SavedText, User, get_db
from app.services.migrations import migrate_analysis_data

router = APIRouter(tags=["Saved Texts"])


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

    result = []
    for text in texts:
        analysis_data = json.loads(text.analysis_data)
        migrated_data = migrate_analysis_data(analysis_data)
        result.append(
            {
                "id": text.id,
                "title": text.title,
                "content": text.content,
                "date": text.created_at.isoformat(),
                "analysisData": migrated_data,
                "tags": text.tags,
                "reading_progress": text.reading_progress or 0,
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
