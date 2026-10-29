"""
Cloze-mode review support.

For each word a user is reviewing in cloze mode, we want a sentence from
one of the user's *own* saved texts where that word appears, with the
word blanked out. That makes cloze cards inherently personal: you're
recalling vocabulary in the contexts you actually read.

Pipeline:
1. UserWord.sample_sentence is the cached sentence (Text, nullable).
   The reader sends the sentence a word was marked in
   (`adopt_sentence`), so most words carry the context they were met in.
2. When a review needs a card with no cached sentence,
   `populate_sample_sentence` asks the database for the newest saved
   text containing the word and stores the first hit, falling back to
   the shortest sentence of the bundled library that uses the word. If
   nothing matches, the card stays empty and the cloze queue drops it.
   Misses are remembered per user (in memory) until one of their texts
   is saved, edited or deleted (`forget_misses`), so a long tail of
   sentence-less cards doesn't rescan on every session.
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
import time

from sqlalchemy.orm import Session

from app.database import SavedText, UserWord
from app.services import library
from app.state import hsk_vocab

# Chinese / Western sentence-final punctuation. We keep the terminator
# attached to the preceding sentence so the rendered cloze looks natural
# ("我吃苹果。" rather than "我吃苹果").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；…\.!?;])\s*")
# Some upper bound so a runaway pasted paragraph doesn't return a huge
# wall of text as a "sentence". Roughly 2-3 lines of Chinese reading.
_MAX_SENTENCE_CHARS = 80

# user_id -> {word: monotonic time of the miss}. A miss stays valid until
# the user's texts change (forget_misses) or the TTL runs out, whichever
# comes first; the TTL only bounds memory and covers texts written by a
# code path that forgets to call forget_misses.
_MISS_TTL_SECONDS = 6 * 3600
_MAX_MISSES_PER_USER = 5000
_misses: dict[int, dict[str, float]] = {}


def forget_misses(user_id: int | None = None) -> None:
    """Drop remembered misses for one user (or everyone)."""
    if user_id is None:
        _misses.clear()
    else:
        _misses.pop(user_id, None)


def _is_known_miss(user_id: int, word: str) -> bool:
    seen = _misses.get(user_id, {}).get(word)
    return seen is not None and time.monotonic() - seen < _MISS_TTL_SECONDS


def _remember_miss(user_id: int, word: str) -> None:
    bucket = _misses.setdefault(user_id, {})
    if len(bucket) >= _MAX_MISSES_PER_USER:
        bucket.clear()
    bucket[word] = time.monotonic()


def split_sentences(text: str) -> list[str]:
    """Cheaply split Chinese text into sentence-sized chunks."""
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


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

    Takes the newest saved text containing the word (one `LIKE … LIMIT 1`
    query) so contemporary reading takes priority over old imports.
    Returns the chosen sentence, or None if no saved text contains the
    word — that miss is cached until `forget_misses(user_id)`.
    """
    if row.sample_sentence:
        return row.sample_sentence
    if not row.word or _is_known_miss(row.user_id, row.word):
        return None
    hit = (
        db.query(SavedText.content, SavedText.title)
        .filter(
            SavedText.user_id == row.user_id,
            SavedText.content.contains(row.word, autoescape=True),
        )
        .order_by(SavedText.created_at.desc())
        .limit(1)
        .first()
    )
    sentence = find_sentence_for_word(hit[0], row.word) if hit else None
    if sentence:
        row.sample_sentence = sentence
        row.sample_source = _source_label(hit[1])
        return sentence
    example = library.example_sentence(row.word, _hsk_level_number(row.word))
    if example:
        row.sample_sentence, title = example
        row.sample_source = _source_label(title)
        return row.sample_sentence
    _remember_miss(row.user_id, row.word)
    return None


def adopt_sentence(row: UserWord, sentence: str | None, source: str | None) -> bool:
    """Keep the sentence a word was marked in as its sample sentence. The
    first context wins: a row that already has one keeps it. The sentence
    must contain the word; an overlong one is cut around it."""
    if row.sample_sentence or not sentence or not row.word:
        return False
    picked = find_sentence_for_word(sentence.strip(), row.word)
    if not picked:
        return False
    row.sample_sentence = picked
    row.sample_source = _source_label(source)
    return True


def _source_label(title: str | None) -> str | None:
    title = (title or "").strip()
    return title[:160] or None


def _hsk_level_number(word: str) -> int | None:
    """3 for "new-3", 7 for "new-7-9"; None outside the HSK list."""
    level = (hsk_vocab.get(word) or {}).get("level_new") or ""
    m = re.match(r"new-(\d+)", level)
    return int(m.group(1)) if m else None


__all__ = [
    "adopt_sentence",
    "find_sentence_for_word",
    "forget_misses",
    "make_cloze_template",
    "populate_sample_sentence",
    "split_sentences",
]
