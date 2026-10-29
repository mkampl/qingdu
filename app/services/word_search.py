"""
Free-text search over a user's word rows (the /words search box).

A query matches when any of these hits:
- the word itself, in either script (rows are Simplified-canonical, the
  user may type Traditional);
- the pinyin, ignoring tones, spaces and tone numbers, so "hao", "hao3"
  and "hǎo" all find 好 (hǎo);
- the stored English meaning, case-insensitive.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import func, or_
from sqlalchemy.sql.elements import ColumnElement

from app.database import User, UserWord
from app.services.script import script_variants, to_canonical

# Every toned / umlauted letter that shows up in stored pinyin, mapped to
# its bare ASCII letter. SQLite's lower() only folds ASCII, so toned
# capitals (Ā lā bó yǔ) are listed explicitly.
_TONE_MAP = {
    **dict.fromkeys("āáǎàĀÁǍÀ", "a"),
    **dict.fromkeys("ēéěèĒÉĚÈ", "e"),
    **dict.fromkeys("īíǐìĪÍǏÌ", "i"),
    **dict.fromkeys("ōóǒòŌÓǑÒ", "o"),
    **dict.fromkeys("ūúǔùŪÚǓÙ", "u"),
    **dict.fromkeys("ǖǘǚǜüǕǗǙǛÜ", "u"),
    **dict.fromkeys("ńňǹŃŇǸ", "n"),
    "ḿ": "m",
}
# Separators and tone numbers, dropped from both sides before comparing.
_STRIP = (" ", "'", "’", "-", "1", "2", "3", "4", "5")

_PINYIN_QUERY = re.compile(r"^[a-z]+$")


def pinyin_key(text: str) -> str:
    """Tone-free, space-free, lower-case form of a pinyin string.

    "Nǐ hǎo" -> "nihao", "ni3 hao3" -> "nihao", "lü4" / "lv4" -> "lu".
    """
    if not text:
        return ""
    s = "".join(_TONE_MAP.get(ch, ch) for ch in unicodedata.normalize("NFC", text))
    s = s.lower().replace("v", "u")
    for ch in _STRIP:
        s = s.replace(ch, "")
    # Decomposed input (tone mark as a separate combining character).
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))


def search_clause(term: str, user: User | None) -> ColumnElement[bool] | None:
    """SQL filter for a search box query, or None for a blank query."""
    term = (term or "").strip()
    if not term:
        return None
    variants = script_variants(term) | {to_canonical(term, user)}
    clauses = [UserWord.word.contains(v, autoescape=True) for v in sorted(variants)]

    key = pinyin_key(term)
    if key and _PINYIN_QUERY.match(key):
        # pinyin_key() is registered as an SQL function on each SQLite
        # connection (app.database).
        clauses.append(func.pinyin_key(UserWord.pinyin).contains(key, autoescape=True))

    clauses.append(func.lower(UserWord.meaning).contains(term.lower(), autoescape=True))
    return or_(*clauses)
