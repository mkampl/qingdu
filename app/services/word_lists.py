"""The user's vocabulary lists and the glossaries they give a text."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import User, VocabularyList

logger = logging.getLogger(__name__)


def owned_list(db: Session, user: User, list_id: int) -> VocabularyList:
    """Return the list if it belongs to `user`, else 404."""
    vocab_list = (
        db.query(VocabularyList)
        .filter(VocabularyList.id == list_id, VocabularyList.user_id == user.id)
        .first()
    )
    if not vocab_list:
        raise HTTPException(status_code=404, detail="List not found")
    return vocab_list


def load_sections(vocab_list: VocabularyList) -> list[dict]:
    """Stored sections, defensively: lists saved before request validation
    can hold sections without a name or words, which would KeyError every
    later mutation."""
    try:
        raw = json.loads(vocab_list.sections) if vocab_list.sections else []
    except (TypeError, ValueError):
        logger.warning("vocab list %s has unreadable sections; treating as empty", vocab_list.id)
        return []
    sections = []
    for section in raw if isinstance(raw, list) else []:
        if not isinstance(section, dict):
            continue
        section.setdefault("name", "")
        words = section.get("words")
        section["words"] = [
            w for w in (words if isinstance(words, list) else []) if isinstance(w, dict)
        ]
        for w in section["words"]:
            w.setdefault("hanzi", "")
        sections.append(section)
    return sections


def list_words(vocab_list: VocabularyList) -> list[dict]:
    """Every word entry of a list, in section order."""
    return [
        w
        for section in load_sections(vocab_list)
        for w in section["words"]
        if (w.get("hanzi") or "").strip()
    ]


def build_glossary(
    db: Session,
    user: User | None,
    list_ids: list[int] | None,
) -> dict[str, dict]:
    """
    Resolve a text's glossary choice to a {word: {pinyin, meaning, list_name}} map.

    Each text picks its own glossaries (the reader's Glossaries picker);
    a list's glossary flag only offers it there. So:
      - user is None              -> empty map (anonymous can't use a glossary)
      - list_ids None or []       -> no glossary (a new text starts without)
      - list_ids == [3, 5]        -> those of the user's lists

    Multi-list conflicts: later-created lists win (ORDER BY created_at ASC,
    so the most recently-curated glossary takes priority).
    """
    if user is None or not list_ids:
        return {}

    lists = (
        db.query(VocabularyList)
        .filter(VocabularyList.user_id == user.id, VocabularyList.id.in_(list_ids))
        .order_by(VocabularyList.created_at.asc())
        .all()
    )

    out: dict[str, dict] = {}
    for vl in lists:
        # Iteration order is oldest-list first, so newer lists naturally
        # overwrite. Inside one list, last word wins.
        for word in list_words(vl):
            out[word["hanzi"].strip()] = {
                "pinyin": (word.get("pinyin") or "").strip(),
                "meaning": (word.get("meaning") or "").strip(),
                "meanings": word.get("meanings") or [],
                "list_name": vl.name,
                "list_id": vl.id,
            }
    return out
