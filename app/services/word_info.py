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
  3. `app.state.unknown_word_cache` — populated by reader-side analysis
     when the user has just seen the word in a text. TTL'd, so this only
     helps when the insertion is fresh.
  4. Compound assembly from HSK characters — for words like 道德 made
     entirely of HSK-known characters, we glue per-char pinyin and
     meanings together. Lossy but always better than nothing.
  5. Pure pypinyin fallback — meaning stays empty, but at least the
     learner can pronounce the card.
"""

from __future__ import annotations

from pypinyin import Style, lazy_pinyin

from app.state import cedict_vocab, hsk_vocab, unknown_word_cache


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

    cached = unknown_word_cache.get(word)
    if cached:
        return cached.get("pinyin", "") or "", cached.get("meaning", "") or ""

    chars = list(word)
    if chars and all(c in hsk_vocab for c in chars):
        pinyins = [hsk_vocab[c].get("pinyin", "") for c in chars]
        meanings = [hsk_vocab[c].get("meaning", "") for c in chars if hsk_vocab[c].get("meaning")]
        return " ".join(p for p in pinyins if p), " + ".join(m for m in meanings if m)

    return " ".join(lazy_pinyin(word, style=Style.TONE)), ""


__all__ = ["lookup_pinyin_meaning"]
