"""In-memory cache + recommendation logic for the bundled HSK library.

The library lives under `app/data/library/hsk{1..9}/{slug}.json`. Each file
is a complete Qingdu-shaped reading text — pre-analyzed at maintainer build
time so the server never re-analyzes a library text and never spends a
DeepL token on bundled content.

Loaded once at module import. ~21 MB across 180 files; iterating the
manifest stays trivial.

The stored analyses carry the glosses the dictionary had at build time.
`client_entry()` re-resolves them against the current dictionary the first
time a text is opened (see `gloss_refresh`), so pinyin and meaning fixes
reach the library without regenerating the files.
"""

import json
import threading
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services import dict_data
from app.services.gloss_refresh import refresh_analysis

LIBRARY_ROOT = Path(__file__).resolve().parent.parent / "data" / "library"


@lru_cache(maxsize=1)
def _all_entries() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not LIBRARY_ROOT.exists():
        return items
    for level_dir in sorted(LIBRARY_ROOT.iterdir()):
        if not level_dir.is_dir():
            continue
        for f in sorted(level_dir.glob("*.json")):
            items.append(json.loads(f.read_text(encoding="utf-8")))
    return items


def _unique_cjk_words(analyzed: dict | None) -> set[str]:
    if not analyzed:
        return set()
    out: set[str] = set()
    for w in analyzed.get("words", []):
        token = w.get("text") or ""
        if not token or not w.get("is_hsk") and not w.get("hsk_level"):
            continue
        # Cheap CJK check — any 一-鿿 char
        if any("一" <= c <= "鿿" for c in token):
            out.add(token)
    return out


def manifest() -> list[dict[str, Any]]:
    """Metadata-only listing — no full text, no analyzed payload."""
    return [
        {
            "slug": e["slug"],
            "title": e["title"],
            "hsk_level": e["hsk_level"],
            "topic": e["topic"],
            "grammar_pattern": e.get("grammar_pattern"),
            "char_count": e["char_count"],
            "total_unique_words": len(_unique_cjk_words(e.get("analyzed"))),
            "has_quiz": bool(e.get("questions")),
        }
        for e in _all_entries()
    ]


def get(slug: str) -> dict[str, Any] | None:
    for e in _all_entries():
        if e["slug"] == slug:
            return e
    return None


_refresh_lock = threading.Lock()


def client_entry(slug: str) -> dict[str, Any] | None:
    """The text as the reader gets it: glosses brought up to the current
    dictionary, quiz answer key left out (the quiz endpoint serves the
    questions; grading stays server-side)."""
    entry = get(slug)
    if entry is None:
        return None
    analyzed = entry.get("analyzed")
    if isinstance(analyzed, dict):
        with _refresh_lock:
            refresh_analysis(analyzed, dict_data.dict_version())
    out = {k: v for k, v in entry.items() if k != "questions"}
    out["has_quiz"] = bool(entry.get("questions"))
    return out


# Sentence-final punctuation for the sentence index below.
_SENTENCE_END = frozenset("。！？；…!?;")
_MAX_EXAMPLE_CHARS = 60


@lru_cache(maxsize=1)
def _sentence_index() -> list[tuple[int, str, str, frozenset[str]]]:
    """(hsk_level, title, sentence, word tokens) for every sentence of the
    bundled texts, built from the stored segmentation so a word only
    matches where it stands as a word (会 is not found inside 社会)."""
    rows: list[tuple[int, str, str, frozenset[str]]] = []
    for e in _all_entries():
        words = (e.get("analyzed") or {}).get("words") or []
        text, tokens = "", set()
        for w in words:
            token = w.get("text") or ""
            if token == "\n":
                token = ""
            text += token
            if token.strip():
                tokens.add(token)
            if token and token[-1] in _SENTENCE_END or not token:
                if text.strip() and tokens:
                    rows.append((e["hsk_level"], e["title"], text.strip(), frozenset(tokens)))
                text, tokens = "", set()
        if text.strip() and tokens:
            rows.append((e["hsk_level"], e["title"], text.strip(), frozenset(tokens)))
    return rows


def example_sentence(word: str, max_level: int | None = None) -> tuple[str, str] | None:
    """Shortest library sentence that uses `word` as a word, preferring
    texts at or below `max_level`. Returns (sentence, text title)."""
    best: tuple[int, int, str, str] | None = None
    for level, title, sentence, tokens in _sentence_index():
        if word not in tokens or len(sentence) > _MAX_EXAMPLE_CHARS:
            continue
        above = 1 if max_level is not None and level > max_level else 0
        key = (above, len(sentence), sentence, title)
        if best is None or key < best:
            best = key
    return (best[2], best[3]) if best else None


def questions(slug: str) -> list[dict[str, Any]] | None:
    """Raw questions (including `answer_index`) — server-side grading only."""
    entry = get(slug)
    if entry is None:
        return None
    qs = entry.get("questions")
    return qs if qs else None


def quiz_questions(slug: str) -> list[dict[str, Any]] | None:
    """Client-safe questions — `answer_index` stripped so it never ships to
    the browser before the quiz is graded."""
    qs = questions(slug)
    if qs is None:
        return None
    return [{"prompt": q["prompt"], "options": q["options"]} for q in qs]


def for_user(
    known_set: set[str],
    *,
    min_score: float = 0.85,
    max_score: float = 0.98,
    limit: int = 12,
    hsk_levels: Iterable[int] | None = None,
) -> list[dict[str, Any]]:
    """Library entries in the user's i+1 comprehension zone.

    Returns a list of slim recommendation rows (no full text / analyzed),
    sorted by comprehension score descending so the easiest-feeling reads
    show first. Includes a couple of `learning_word_count` hints so the
    frontend can highlight "you'd encounter 7 new words" affordances.
    """
    rows: list[dict[str, Any]] = []
    for e in _all_entries():
        if hsk_levels is not None and e["hsk_level"] not in hsk_levels:
            continue
        unique = _unique_cjk_words(e.get("analyzed"))
        total = len(unique)
        if total == 0:
            continue
        known = sum(1 for w in unique if w in known_set)
        score = round(known / total, 4)
        if not (min_score <= score <= max_score):
            continue
        rows.append(
            {
                "slug": e["slug"],
                "title": e["title"],
                "hsk_level": e["hsk_level"],
                "topic": e["topic"],
                "char_count": e["char_count"],
                "total_unique_words": total,
                "known_unique": known,
                "new_words": total - known,
                "comprehension_score": score,
                "preview": e["text"][:80],
            }
        )
    rows.sort(key=lambda r: (-r["comprehension_score"], r["hsk_level"]))
    return rows[:limit]
