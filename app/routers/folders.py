"""Folders of saved texts (services/text_folders).

Folders nest; a text lives in one folder or at the top level. Moving a
text is a PATCH of its `folder_id` on /api/texts/{id}; the order of the
texts inside a folder is set with POST /api/texts/order.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.database import TextFolder, User, get_db
from app.services import text_folders

router = APIRouter(tags=["Text folders"])

FolderName = Field(..., min_length=1, max_length=120)


class FolderCreate(BaseModel):
    name: str = FolderName
    parent_id: int | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    # Moving needs the key present; null moves the folder to the top level.
    parent_id: int | None = None
    move: bool = False


class TextOrder(BaseModel):
    folder_id: int | None = None
    text_ids: list[int] = Field(..., max_length=2000)


def _payload(folder: TextFolder) -> dict:
    return {
        "id": folder.id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "position": folder.position,
    }


@router.get("/api/folders")
def list_folders(user: User = Depends(require_auth), db: Session = Depends(get_db)) -> list:
    """Every folder of the user; the client builds the tree."""
    rows = (
        db.query(TextFolder)
        .filter(TextFolder.user_id == user.id)
        .order_by(TextFolder.position.is_(None), TextFolder.position, TextFolder.name)
        .all()
    )
    return [_payload(f) for f in rows]


@router.post("/api/folders")
def create_folder(
    body: FolderCreate, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    text_folders.owned(db, user.id, body.parent_id)
    folder = TextFolder(user_id=user.id, name=body.name.strip(), parent_id=body.parent_id)
    db.add(folder)
    db.commit()
    return _payload(folder)


@router.patch("/api/folders/{folder_id}")
def update_folder(
    folder_id: int,
    body: FolderUpdate,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Rename a folder, or move it (`move: true` with the new `parent_id`)."""
    folder = text_folders.owned(db, user.id, folder_id)
    if body.name is not None:
        folder.name = body.name.strip()
    if body.move:
        parent = text_folders.owned(db, user.id, body.parent_id)
        text_folders.check_parent(db, folder, parent)
        folder.parent_id = body.parent_id
    db.commit()
    return _payload(folder)


@router.delete("/api/folders/{folder_id}")
def delete_folder(
    folder_id: int, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    """Delete a folder. Its texts and subfolders move up one level; no text
    is deleted."""
    folder = text_folders.owned(db, user.id, folder_id)
    text_folders.delete(db, folder)
    db.commit()
    return {"message": "Folder deleted"}


@router.post("/api/texts/order")
def order_texts(
    body: TextOrder, user: User = Depends(require_auth), db: Session = Depends(get_db)
) -> dict:
    """Set the reading order of a folder's texts (all of them, in order)."""
    if body.folder_id is None:
        raise HTTPException(status_code=400, detail="The top level has no order")
    text_folders.owned(db, user.id, body.folder_id)
    texts = {t.id: t for t in text_folders.siblings(db, user.id, body.folder_id)}
    if sorted(body.text_ids) != sorted(texts):
        raise HTTPException(status_code=400, detail="Send every text of the folder once")
    for i, text_id in enumerate(body.text_ids):
        texts[text_id].position = i
    db.commit()
    return {"message": "Order saved"}


__all__ = ["router"]
