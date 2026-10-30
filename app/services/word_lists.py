"""The user's vocabulary lists and the glossaries they give a text."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.database import User, VocabularyList


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
        try:
            sections = json.loads(vl.sections) if vl.sections else []
        except (ValueError, TypeError):
            continue
        for section in sections:
            for word in section.get("words", []) or []:
                hanzi = (word.get("hanzi") or "").strip()
                if not hanzi:
                    continue
                # Iteration order is oldest-list first, so newer lists
                # naturally overwrite. Inside one list, last word wins.
                out[hanzi] = {
                    "pinyin": (word.get("pinyin") or "").strip(),
                    "meaning": (word.get("meaning") or "").strip(),
                    "meanings": word.get("meanings") or [],
                    "list_name": vl.name,
                    "list_id": vl.id,
                }
    return out
