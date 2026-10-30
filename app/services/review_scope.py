"""A review session focused on one text or one vocab list.

A scope narrows the review queue to the words the user pre-learned for a
text (text_words) or the words of one of their vocab lists, and names the
meaning that text or list gives each word, so the card can lead with it
("focus gloss") and show the dictionary meaning beneath.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.database import TextWord, User, UserWord
from app.services.gloss_refresh import is_user_meaning
from app.services.script import to_canonical
from app.services.word_lists import list_words, owned_list


@dataclass
class Scope:
    kind: str  # 'text' | 'list'
    title: str | None
    clause: ColumnElement[bool]
    # word -> (gloss source, gloss tag) of the text's or list's own meaning.
    focus: dict[str, tuple[str, str | None]] = field(default_factory=dict)


def resolve(
    db: Session, user: User, text_key: str | None = None, list_id: int | None = None
) -> Scope | None:
    if text_key:
        rows = (
            db.query(TextWord.word, TextWord.title, TextWord.gloss_source, TextWord.gloss_tag)
            .filter(TextWord.user_id == user.id, TextWord.text_key == text_key)
            .all()
        )
        words = select(TextWord.word).where(
            TextWord.user_id == user.id, TextWord.text_key == text_key
        )
        return Scope(
            kind="text",
            title=next((r.title for r in rows if r.title), None),
            clause=UserWord.word.in_(words),
            focus={r.word: (r.gloss_source, r.gloss_tag) for r in rows if r.gloss_source},
        )
    if list_id is not None:
        vocab_list = owned_list(db, user, list_id)
        focus: dict[str, tuple[str, str | None]] = {}
        words: set[str] = set()
        for w in list_words(vocab_list):
            hanzi = to_canonical(w["hanzi"].strip(), user)
            words.add(hanzi)
            if is_user_meaning(hanzi, w.get("meaning")):
                focus[hanzi] = ("list", vocab_list.name)
        return Scope(
            kind="list",
            title=vocab_list.name,
            clause=UserWord.word.in_(sorted(words)),
            focus=focus,
        )
    return None


def focus_gloss(scope: Scope | None, row: UserWord) -> dict | None:
    """The row's gloss from the scope's text or list, if it has one."""
    if scope is None:
        return None
    want = scope.focus.get(row.word)
    if want is None:
        return None
    source, tag = want
    for g in row.glosses or []:
        if g.source == source and (g.source_tag or None) == (tag or None):
            return {
                "source": g.source,
                "tag": g.source_tag,
                "meaning": g.meaning,
                "pinyin": g.pinyin,
            }
    return None


__all__ = ["Scope", "focus_gloss", "resolve"]
