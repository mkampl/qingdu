"""
Cloze-mode review support — Phase B remainder.

For each word a user is reviewing in cloze mode, we want a sentence from
one of the user's *own* saved texts where that word appears, with the
word blanked out. That makes cloze cards inherently personal: you're
recalling vocabulary in the contexts you actually read.

Pipeline:
1. UserWord.sample_sentence is the cached sentence (Text, nullable).
2. When a cloze review needs to render a card with no cached sentence,
   `populate_sample_sentence` scans the user's saved texts for a
   sentence containing the word and stores the first hit. If nothing
   matches, the card stays empty and the queue endpoint drops it from
   the cloze rotation.
3. `make_cloze_template(sentence, word)` produces the visible "fill in
   the blank" string by replacing the first occurrence of the word
   with ``___``. The card payload also carries the bare word so the
   SPA can grade the user's input.

Sentence segmentation is intentionally cheap: we split on Chinese
sentence-final punctuation (。！？；) plus their full-width-spaced /
Western equivalents. No jieba, no LLM, no extra round-trips.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.database import SavedText, UserWord

# Chinese / Western sentence-final punctuation. We keep the terminator
# attached to the preceding sentence so the rendered cloze looks natural
# ("我吃苹果。" rather than "我吃苹果").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；…\.!?;])\s*")
# Some upper bound so a runaway pasted paragraph doesn't return a huge
# wall of text as a "sentence". Roughly 2-3 lines of Chinese reading.
_MAX_SENTENCE_CHARS = 80


def split_sentences(text: str) -> list[str]:
    """Cheaply split Chinese text into sentence-sized chunks."""
    if not text:
        return []
    raw = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    return raw


def find_sentence_for_word(text: str, word: str) -> str | None:
    """First sentence in `text` containing `word`, or None.

    Prefers shorter sentences when several contain the word — shorter
    cloze prompts read better and let FSRS test recall instead of
    reading comprehension. Caps the returned sentence at
    ``_MAX_SENTENCE_CHARS``; if every candidate is longer than that we
    still return the shortest, but truncated around the word.
    """
    if not text or not word:
        return None
    candidates = [s for s in split_sentences(text) if word in s]
    if not candidates:
        return None
    candidates.sort(key=len)
    best = candidates[0]
    if len(best) <= _MAX_SENTENCE_CHARS:
        return best
    # Truncate around the first occurrence so the word stays visible.
    idx = best.find(word)
    half = _MAX_SENTENCE_CHARS // 2
    start = max(0, idx - half)
    end = min(len(best), start + _MAX_SENTENCE_CHARS)
    snippet = best[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(best):
        snippet = snippet + "…"
    return snippet


def make_cloze_template(sentence: str, word: str) -> str:
    """Render the sentence with the word's first occurrence blanked."""
    if not sentence or not word:
        return sentence
    idx = sentence.find(word)
    if idx < 0:
        return sentence
    return sentence[:idx] + "___" + sentence[idx + len(word) :]


def populate_sample_sentence(row: UserWord, db: Session) -> str | None:
    """Find and store a sample sentence for a single UserWord row.

    Scans the user's saved texts in newest-first order so contemporary
    reading takes priority over old imports. Returns the chosen sentence
    or None if no saved text contains the word.
    """
    if row.sample_sentence:
        return row.sample_sentence
    texts = (
        db.query(SavedText.content)
        .filter(SavedText.user_id == row.user_id)
        .order_by(SavedText.created_at.desc())
        .all()
    )
    for (content,) in texts:
        if not content or row.word not in content:
            continue
        sentence = find_sentence_for_word(content, row.word)
        if sentence:
            row.sample_sentence = sentence
            return sentence
    return None


__all__ = [
    "find_sentence_for_word",
    "make_cloze_template",
    "populate_sample_sentence",
    "split_sentences",
]
