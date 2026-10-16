"""Folders of saved texts: nesting, the order of the texts in a folder, and
where a text stands in its folder (for "2 / 6" and previous / next).

A text lives in at most one folder (`saved_texts.folder_id`, NULL = top
level). Inside a folder texts are read in `position` order; texts without
a position follow, oldest first. The top level keeps its newest-first list
and has no numbering.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SavedText, TextFolder

# Deepest folder chain walked (cycle guard for damaged data).
MAX_DEPTH = 32


def owned(db: Session, user_id: int, folder_id: int | None) -> TextFolder | None:
    """The user's folder, None for the top level; 404 for anything else."""
    if folder_id is None:
        return None
    folder = (
        db.query(TextFolder)
        .filter(TextFolder.id == folder_id, TextFolder.user_id == user_id)
        .first()
    )
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


def path(db: Session, folder: TextFolder | None) -> list[TextFolder]:
    """The folder and its parents, top level first."""
    out: list[TextFolder] = []
    seen: set[int] = set()
    while folder is not None and folder.id not in seen and len(out) < MAX_DEPTH:
        out.append(folder)
        seen.add(folder.id)
        folder = db.get(TextFolder, folder.parent_id) if folder.parent_id else None
    return list(reversed(out))


def check_parent(db: Session, folder: TextFolder, parent: TextFolder | None) -> None:
    """A folder can't move into itself or into one of its own subfolders."""
    if parent is not None and any(f.id == folder.id for f in path(db, parent)):
        raise HTTPException(status_code=400, detail="A folder can't go inside itself")


def siblings(db: Session, user_id: int, folder_id: int | None) -> list[SavedText]:
    """The texts of one folder in reading order."""
    q = db.query(SavedText).filter(SavedText.user_id == user_id)
    q = q.filter(
        SavedText.folder_id.is_(None) if folder_id is None else SavedText.folder_id == folder_id
    )
    return q.order_by(
        SavedText.position.is_(None),
        SavedText.position,
        SavedText.created_at,
        SavedText.id,
    ).all()


def next_position(db: Session, user_id: int, folder_id: int | None) -> int | None:
    """Position for a text added at the end of a folder (None at top level)."""
    if folder_id is None:
        return None
    top = (
        db.query(func.max(SavedText.position))
        .filter(SavedText.user_id == user_id, SavedText.folder_id == folder_id)
        .scalar()
    )
    count = (
        db.query(func.count(SavedText.id))
        .filter(SavedText.user_id == user_id, SavedText.folder_id == folder_id)
        .scalar()
    )
    return max(top if top is not None else -1, count - 1) + 1


def series(db: Session, text: SavedText) -> dict | None:
    """Where a text stands in its folder: the folder path, its number and
    its neighbours. None at top level."""
    if text.folder_id is None:
        return None
    folder = db.get(TextFolder, text.folder_id)
    if folder is None:
        return None
    ids = [t.id for t in siblings(db, text.user_id, text.folder_id)]
    i = ids.index(text.id)
    return {
        "folder_id": folder.id,
        "path": [{"id": f.id, "name": f.name} for f in path(db, folder)],
        "index": i + 1,
        "count": len(ids),
        "prev_id": ids[i - 1] if i > 0 else None,
        "next_id": ids[i + 1] if i + 1 < len(ids) else None,
    }


def delete(db: Session, folder: TextFolder) -> None:
    """Remove a folder; its texts and subfolders move up one level."""
    db.query(SavedText).filter(SavedText.folder_id == folder.id).update(
        {SavedText.folder_id: folder.parent_id, SavedText.position: None},
        synchronize_session=False,
    )
    db.query(TextFolder).filter(TextFolder.parent_id == folder.id).update(
        {TextFolder.parent_id: folder.parent_id}, synchronize_session=False
    )
    db.delete(folder)


__all__ = [
    "check_parent",
    "delete",
    "next_position",
    "owned",
    "path",
    "series",
    "siblings",
]
