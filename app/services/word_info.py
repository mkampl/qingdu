"""
Synchronous best-effort pinyin + meaning lookup for a Chinese word.

Used by the word-state mutators and the daily auto-enrol to populate
the snapshot columns on UserWord at insert time. No network — only
in-process data sources — so it's safe to call from any request handler
without adding latency.

Fallback order:
  1. The full HSK vocab (`app.state.hsk_vocab`) — covers anything in the
     upstream complete-hsk-vocabulary list. Meanings here have already
     been overlaid with CC-CEDICT's richer glosses at startup.
  2. `app.state.cedict_vocab` — the full ~120k CC-CEDICT, used for words
     not in HSK (literary terms, place names, classical Chinese).
  3. Anything else is not a dictionary word (很多, 我来, 洗衣服): pypinyin
     gives the reading and the meaning stays empty. Gluing the parts'
     glosses together ("very + many") made fake entries that ended up on
     review cards; `word_parts` lists the parts separately instead.
"""

from __future__ import annotations

from pypinyin import Style, lazy_pinyin

from app.services.lexicon import split_into_known
from app.state import cedict_vocab, hsk_vocab


def lookup_pinyin_meaning(word: str) -> tuple[str, str]:
    """Return (pinyin, meaning). Either field may be empty if not found."""
    word = (word or "").strip()
    if not word:
        return "", ""

    entry = hsk_vocab.get(word)
    if entry:
        return entry.get("pinyin", "") or "", entry.get("meaning", "") or ""

    cedict_entry = cedict_vocab.get(word)
    if cedict_entry:
        return cedict_entry.get("pinyin", "") or "", cedict_entry.get("meaning", "") or ""

    return " ".join(lazy_pinyin(word, style=Style.TONE)), ""


def word_parts(word: str, extra=()) -> list[dict]:
    """Dictionary breakdown of a token that is not a word itself:
    [{word, pinyin, meaning}] for each known sub-word. Empty for words the
    dictionaries know (they need no breakdown) and for single characters."""
    word = (word or "").strip()
    if len(word) <= 1 or word in hsk_vocab or word in cedict_vocab:
        return []
    parts = []
    for part in split_into_known(word, extra):
        pinyin, meaning = lookup_pinyin_meaning(part)
        parts.append({"word": part, "pinyin": pinyin, "meaning": meaning})
    return parts


__all__ = ["lookup_pinyin_meaning", "word_parts"]
