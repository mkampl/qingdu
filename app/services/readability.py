"""How readable a text is for one user — "make this text readable".

A text reads comfortably once about 95 % of its running words are known;
the rest can be guessed from context. This module measures that against
the user's own word states and lists the words that are still missing.

Counting rules:
- Every occurrence counts (running tokens, not distinct words): a word
  that appears five times weighs five times as much.
- Only Chinese words count. Punctuation, Latin text and digits are left
  out. A token that is not a dictionary word (a phrase such as 洗衣服)
  counts as the dictionary words it is made of.
- Known: state 'known', state 'ignored' (the user chose not to learn it,
  names for example), or 'learning' with FSRS stability of at least one
  day. In progress: 'learning' below that, such as a word added today.
  Everything else is missing.
- `to_unlock` is how many missing words, most frequent first, still have
  to be learned to reach the threshold once the words in progress are
  known as well.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.database import UserWord
from app.services.lexicon import (
    is_cjk_word,
    is_lexical_word,
    split_into_known,
    user_word_sources,
)
from app.services.word_info import lookup_pinyin_meaning
from app.state import hsk_vocab

UNLOCK_THRESHOLD = 0.95
KNOWN_STABILITY_DAYS = 1.0

# Most missing words a response lists; the summary numbers always cover
# the whole text.
MAX_MISSING_LISTED = 400

_CHUNK = 500


@dataclass
class WordCounts:
    """Occurrences per word, in order of first appearance."""

    counts: dict[str, int] = field(default_factory=dict)

    def add(self, word: str) -> None:
        self.counts[word] = self.counts.get(word, 0) + 1

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def count_words(
    tokens: Iterable[str],
    *,
    extra: Collection[str] = (),
    db: Session | None = None,
    user_id: int | None = None,
) -> WordCounts:
    """Count the Chinese words among `tokens` (already canonical script).

    `extra` holds words that count as words although no dictionary has
    them, such as a package's or glossary's own terms."""
    out = WordCounts()
    lexical: dict[str, list[str]] = {}
    own: set[str] | None = None
    for raw in tokens:
        token = (raw or "").strip()
        if not token or not is_cjk_word(token):
            continue
        parts = lexical.get(token)
        if parts is None:
            if token in extra or is_lexical_word(token):
                parts = [token]
            else:
                # The user's own list and package words, loaded once.
                if own is None:
                    own = set(extra)
                    if db is not None and user_id is not None:
                        own |= user_word_sources(db, user_id)
                parts = [token] if token in own else split_into_known(token, own)
            lexical[token] = parts
        for part in parts:
            out.add(part)
    return out


def word_status(db: Session, user_id: int, words: Collection[str]) -> dict[str, str]:
    """'known' or 'in_progress' for the words the user has; missing words
    are left out."""
    status: dict[str, str] = {}
    wanted = list(words)
    for i in range(0, len(wanted), _CHUNK):
        rows = (
            db.query(UserWord.word, UserWord.state, UserWord.stability)
            .filter(UserWord.user_id == user_id, UserWord.word.in_(wanted[i : i + _CHUNK]))
            .all()
        )
        for word, state, stability in rows:
            status[word] = classify(state, stability)
    return status


def classify(state: str | None, stability: float | None) -> str:
    if state in ("known", "ignored"):
        return "known"
    if state == "learning" and (stability or 0) >= KNOWN_STABILITY_DAYS:
        return "known"
    return "in_progress"


@dataclass
class Summary:
    total: int
    unique: int
    known: int
    in_progress: int
    missing: list[tuple[str, int]]
    in_progress_words: list[str]
    threshold: float = UNLOCK_THRESHOLD

    @property
    def known_pct(self) -> float:
        return self.known / self.total if self.total else 1.0

    @property
    def with_progress_pct(self) -> float:
        return (self.known + self.in_progress) / self.total if self.total else 1.0

    @property
    def unlocked(self) -> bool:
        return self.known_pct >= self.threshold

    @property
    def to_unlock(self) -> int:
        """Missing words, most frequent first, needed to reach the
        threshold once the words in progress are known too."""
        if not self.total:
            return 0
        covered = self.known + self.in_progress
        need = self.threshold * self.total
        n = 0
        for _word, count in self.missing:
            if covered >= need - 1e-9:
                break
            covered += count
            n += 1
        return n


def summarize(counts: WordCounts, status: dict[str, str]) -> Summary:
    known = in_progress = 0
    missing: list[tuple[str, int]] = []
    in_progress_words: list[str] = []
    for word, count in counts.counts.items():
        s = status.get(word)
        if s == "known":
            known += count
        elif s == "in_progress":
            in_progress += count
            in_progress_words.append(word)
        else:
            missing.append((word, count))
    # Most frequent first; ties keep the order of first appearance.
    missing.sort(key=lambda wc: -wc[1])
    return Summary(
        total=counts.total,
        unique=len(counts.counts),
        known=known,
        in_progress=in_progress,
        missing=missing,
        in_progress_words=in_progress_words,
    )


def for_user(
    db: Session,
    user_id: int,
    tokens: Iterable[str],
    *,
    extra: Collection[str] = (),
) -> Summary:
    counts = count_words(tokens, extra=extra, db=db, user_id=user_id)
    return summarize(counts, word_status(db, user_id, counts.counts.keys()))


def hsk_level_number(word: str) -> int | None:
    """3 for "new-3", 7 for "new-7-9"; None outside the HSK list."""
    level = (hsk_vocab.get(word) or {}).get("level_new") or ""
    if not level.startswith("new-"):
        return None
    head = level[4:].split("-")[0]
    return int(head) if head.isdigit() else None


def missing_payload(word: str, count: int) -> dict:
    pinyin, meaning = lookup_pinyin_meaning(word)
    return {
        "word": word,
        "count": count,
        "pinyin": pinyin,
        "meaning": meaning,
        "hsk_level": hsk_level_number(word),
    }


__all__ = [
    "KNOWN_STABILITY_DAYS",
    "UNLOCK_THRESHOLD",
    "Summary",
    "WordCounts",
    "classify",
    "count_words",
    "for_user",
    "missing_payload",
    "summarize",
    "word_status",
]
