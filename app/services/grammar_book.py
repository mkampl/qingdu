"""The user's grammar: which points of the grammar catalog they have met in
what they read, the sentences that show them, practice built from those
sentences, and when each point is due again.

Sources:
- texts read to the end: saved texts at 99 % reading progress, library
  texts marked read or with a passed quiz ("met" counts only these);
- the user's other saved texts and the bundled library texts, for more
  example and practice sentences.

A sentence shows a point when the reader's regex patterns find it
(services/grammar, mapped to catalog points) or when the LLM tagged it
(services/grammar_tagging). Each text's sentences and regex hits are
cached in memory, keyed by the analysis' length, so an edited text is
looked at again.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import GrammarProgress, SavedText, SessionLocal, UserLibraryProgress
from app.services import grammar, grammar_catalog, grammar_tagging, library
from app.services.reading_progress import READ_THROUGH, progress_fraction
from app.services.segmentation import _group_sentences, segment_text
from app.services.timestamps import iso_utc

logger = logging.getLogger(__name__)

MAX_SENTENCES = 60
MAX_SENTENCE_CHARS = 80
# Days until a point is due again, by box (raised by a good practice round,
# lowered by a poor one).
INTERVALS = (1, 2, 4, 8, 16, 32, 64)
GOOD_ROUND = 0.8
PRACTICE_ITEMS = 8
CJK = re.compile(r"[㐀-鿿]")


@dataclass
class TextGrammar:
    """What one text holds: its sentences and the regex hits in them."""

    size: int
    sentences: list[str]
    regex: list[tuple[str, str, str]]  # (catalog id, sentence, span)
    translations: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Hit:
    point_id: str
    sentence: str
    span: str
    translation: str | None
    source_key: str  # "saved:<id>" | "library:<slug>"
    source_title: str
    read: bool  # from a text the user has read to the end
    level: int | None = None  # HSK level of a library text


_texts: dict[str, TextGrammar] = {}


def _analyse(key: str, size: int, words: list[dict], translations: dict) -> TextGrammar:
    tokens = [(w.get("text") or "") for w in words if isinstance(w, dict)]
    grouped = _group_sentences(tokens)
    matches, _metas = grammar.detect_patterns(grouped)
    sentences = [
        s.text.strip()
        for _offset, s in grouped
        if CJK.search(s.text) and len(s.text.strip()) <= MAX_SENTENCE_CHARS
    ]
    regex = []
    for m in matches:
        point = grammar_catalog.REGEX_POINT.get(m.pattern_id)
        sentence = grouped[m.sentence_idx][1].text.strip()
        if point and sentence in sentences:
            regex.append((point, sentence, m.span_text))
    tg = TextGrammar(size, sentences, regex, translations)
    _texts[key] = tg
    return tg


def _cached(key: str, size: int) -> TextGrammar | None:
    tg = _texts.get(key)
    return tg if tg and tg.size == size else None


def _sources(db: Session, user_id: int) -> list[tuple[str, str, bool, int | None, TextGrammar]]:
    """(key, title, read, library level, grammar) for every text the user
    can learn from: their saved texts, then the library."""
    out = []
    rows = db.query(
        SavedText.id,
        SavedText.title,
        SavedText.reading_progress,
        func.length(SavedText.analysis_data),
    ).filter(SavedText.user_id == user_id)
    for text_id, title, progress, size in rows:
        key = f"saved:{text_id}"
        tg = _cached(key, size or 0)
        if tg is None:
            raw = db.query(SavedText.analysis_data).filter(SavedText.id == text_id).scalar() or ""
            try:
                data = json.loads(raw) if raw else {}
            except ValueError:
                data = {}
            if not isinstance(data, dict):
                data = {}
            words = data.get("words")
            tg = _analyse(
                key,
                size or 0,
                words if isinstance(words, list) else [],
                data.get("sentence_translations") or {},
            )
        read = progress_fraction(progress) >= READ_THROUGH
        out.append((key, title or "", read, None, tg))

    read_slugs = {
        slug
        for (slug,) in db.query(UserLibraryProgress.slug).filter(
            UserLibraryProgress.user_id == user_id,
            UserLibraryProgress.status.in_(("read", "quiz")),
        )
    }
    for entry in library._all_entries():
        key = f"library:{entry['slug']}"
        tg = _cached(key, 0) or _analyse(
            key, 0, (entry.get("analyzed") or {}).get("words") or [], {}
        )
        out.append((key, entry["title"], entry["slug"] in read_slugs, entry["hsk_level"], tg))
    return out


def prewarm(session_factory=SessionLocal) -> int:
    """Look at every saved text and the library once, at startup, so the
    first visit to the grammar section after a restart is quick (reading
    the stored analyses is the slow part). Returns the texts cached."""
    db = session_factory()
    try:
        user_ids = [u for (u,) in db.query(SavedText.user_id).distinct()]
        for user_id in user_ids or [0]:
            _sources(db, user_id)
    finally:
        db.close()
    return len(_texts)


# LLM tags looked up recently: hash -> tags (absent = not tagged yet).
_tags: dict[str, list[dict]] = {}
_tags_checked = 0.0
TAGS_RECHECK_S = 30


def _llm_tags(sentences: list[str]) -> dict[str, list[dict]]:
    """Stored LLM tags by sentence; untagged sentences are looked up again
    at most every TAGS_RECHECK_S seconds."""
    global _tags_checked
    hashes = {s: grammar_tagging.sentence_hash(s) for s in sentences}
    if time.monotonic() - _tags_checked > TAGS_RECHECK_S:
        missing = [h for h in hashes.values() if h not in _tags]
        _tags.update(grammar_tagging.known(missing))
        _tags_checked = time.monotonic()
    return {s: _tags[h] for s, h in hashes.items() if h in _tags}


def all_hits(db: Session, user_id: int) -> list[Hit]:
    sources = _sources(db, user_id)
    tags = _llm_tags([s for *_rest, tg in sources for s in tg.sentences])
    out: list[Hit] = []
    for key, title, read, level, tg in sources:
        seen: set[tuple[str, str]] = set()
        for point, sentence, span in tg.regex:
            # Once the LLM looked at a sentence, a regex hit it was offered
            # and turned down is a false one (classical 得悟, 得之).
            turned_down = (
                sentence in tags
                and point not in {t["id"] for t in tags[sentence]}
                and point in {c["id"] for c in grammar_catalog.candidates(sentence)}
            )
            if turned_down:
                continue
            seen.add((point, sentence))
            out.append(
                Hit(point, sentence, span, tg.translations.get(sentence), key, title, read, level)
            )
        for sentence in tg.sentences:
            for t in tags.get(sentence, []):
                if (t["id"], sentence) in seen:
                    continue
                seen.add((t["id"], sentence))
                out.append(
                    Hit(
                        t["id"],
                        sentence,
                        t["span"],
                        tg.translations.get(sentence),
                        key,
                        title,
                        read,
                        level,
                    )
                )
    return out


def queue_for_tagging(db: Session, user_id: int) -> int:
    """Queue the sentences of the user's texts for the LLM: texts they read
    first, then the library, then their other texts. Returns how many
    sentences are waiting."""
    if not grammar_tagging.enabled():
        return 0
    sources = _sources(db, user_id)
    ordered = (
        [tg for _k, _t, read, _l, tg in sources if read]
        + [tg for k, _t, read, _l, tg in sources if not read and k.startswith("library:")]
        + [tg for k, _t, read, _l, tg in sources if not read and k.startswith("saved:")]
    )
    return grammar_tagging.enqueue([s for tg in ordered for s in tg.sentences])


def _progress(db: Session, user_id: int) -> dict[str, GrammarProgress]:
    out: dict[str, GrammarProgress] = {}
    for p in db.query(GrammarProgress).filter(GrammarProgress.user_id == user_id):
        out[grammar_catalog.REGEX_POINT.get(p.pattern_id, p.pattern_id)] = p
    return out


def _progress_payload(p: GrammarProgress | None, now: datetime) -> dict | None:
    if p is None:
        return None
    return {
        "box": p.box,
        "due": p.due_at is not None and p.due_at <= now,
        "due_at": iso_utc(p.due_at),
        "last_at": iso_utc(p.last_at),
        "correct": p.correct,
        "total": p.total,
    }


def overview(db: Session, user_id: int, now: datetime | None = None) -> dict:
    """Every catalog point with what the user has met and practised."""
    now = now or datetime.utcnow()
    hits = [h for h in all_hits(db, user_id) if h.read]
    texts: dict[str, set[str]] = {}
    sentences: dict[str, set[str]] = {}
    for h in hits:
        texts.setdefault(h.point_id, set()).add(h.source_key)
        sentences.setdefault(h.point_id, set()).add(h.sentence)
    progress = _progress(db, user_id)
    points = [
        {
            "id": e["id"],
            "level": e["level"],
            "group": e["group"],
            "forms": e["forms"],
            "title": e["title_en"],
            "structure": e["structure"],
            "met_texts": len(texts.get(e["id"], ())),
            "met_sentences": len(sentences.get(e["id"], ())),
            "progress": _progress_payload(progress.get(e["id"]), now),
        }
        for e in grammar_catalog.entries()
    ]
    return {
        "points": points,
        "read_texts": len({h.source_key for h in hits}),
        "analysing": queue_for_tagging(db, user_id),
        "llm": grammar_tagging.enabled(),
    }


def _hit_payload(h: Hit) -> dict:
    return {
        "sentence": h.sentence,
        "span": h.span,
        "translation": h.translation,
        "source_key": h.source_key,
        "source_title": h.source_title,
        "read": h.read,
    }


def point_detail(db: Session, user_id: int, point_id: str) -> dict | None:
    """A point with the sentences that show it: from texts the user has
    read first, then their other texts, then the library (easiest first)."""
    e = grammar_catalog.get(point_id)
    if e is None:
        return None
    seen: set[str] = set()
    groups: dict[str, list[dict]] = {"read": [], "saved": [], "library": []}
    hits = [h for h in all_hits(db, user_id) if h.point_id == e["id"]]
    hits.sort(key=lambda h: (not h.read, h.source_key.startswith("library:"), h.level or 0))
    for h in hits:
        if h.sentence in seen:
            continue
        seen.add(h.sentence)
        group = (
            "read" if h.read else ("library" if h.source_key.startswith("library:") else "saved")
        )
        if len(groups[group]) < MAX_SENTENCES:
            groups[group].append(_hit_payload(h))
    progress = _progress(db, user_id).get(e["id"])
    return {
        **{k: v for k, v in e.items() if k != "no"},
        "title": e["title_en"],
        "sentences": groups,
        "progress": _progress_payload(progress, datetime.utcnow()),
    }


# --- Practice ------------------------------------------------------------------

# Words easily confused with a point's word, for the wrong choices of a gap
# exercise when the catalog has too few of its own.
CONFUSABLE: dict[str, list[str]] = {
    "把": ["被", "给", "让"],
    "被": ["把", "给", "让"],
    "给": ["把", "被", "对"],
    "让": ["被", "把", "给"],
    "所以": ["但是", "而且", "可是"],
    "因为": ["虽然", "如果", "只要"],
    "但是": ["所以", "而且", "因为"],
    "虽然": ["因为", "如果", "只要"],
    "而且": ["但是", "所以", "可是"],
    "如果": ["因为", "虽然", "只有"],
    "就": ["才", "都", "也"],
    "才": ["就", "都", "也"],
    "了": ["过", "着", "的"],
    "过": ["了", "着", "的"],
    "着": ["了", "过", "的"],
    "得": ["的", "地", "了"],
    "的": ["得", "地", "了"],
    "地": ["的", "得", "了"],
    "比": ["跟", "和", "像"],
    "只要": ["只有", "虽然", "因为"],
    "只有": ["只要", "虽然", "因为"],
}


def _cloze(e: dict, h: Hit, rng: random.Random) -> dict | None:
    start = h.sentence.find(h.span)
    for marker in sorted(e.get("markers") or [], key=lambda m: -len(m)):
        at = h.sentence.find(marker, max(start, 0)) if start >= 0 else h.sentence.find(marker)
        if at < 0 or (start >= 0 and at > start + len(h.span)):
            continue
        wrong = [
            w
            for w in (e.get("distractors") or []) + CONFUSABLE.get(marker, [])
            if w != marker and w not in (e.get("markers") or [])
        ]
        wrong = list(dict.fromkeys(wrong))[:3]
        if len(wrong) < 2:
            continue
        choices = [marker, *wrong]
        rng.shuffle(choices)
        return {
            "type": "cloze",
            "before": h.sentence[:at],
            "after": h.sentence[at + len(marker) :],
            "choices": choices,
            "answer": choices.index(marker),
            "sentence": h.sentence,
            "translation": h.translation,
            "source_title": h.source_title,
        }
    return None


def _order(h: Hit, words_of: dict[str, list[str]], rng: random.Random) -> dict | None:
    tokens = words_of.get(h.sentence)
    if not tokens:
        return None
    body = [t for t in tokens if CJK.search(t)]
    if not 4 <= len(body) <= 14:
        return None
    # Chunks of one to three words, 4–6 pieces, punctuation left out.
    n = min(6, max(4, len(body) // 2))
    size = len(body) / n
    pieces = ["".join(body[round(i * size) : round((i + 1) * size)]) for i in range(n)]
    pieces = [p for p in pieces if p]
    if len(set(pieces)) != len(pieces):
        return None
    shuffled = pieces[:]
    for _ in range(5):
        rng.shuffle(shuffled)
        if shuffled != pieces:
            break
    return {
        "type": "order",
        "pieces": shuffled,
        "answer": pieces,
        "sentence": h.sentence,
        "translation": h.translation,
        "source_title": h.source_title,
    }


def _words_by_sentence(sentences: list[str]) -> dict[str, list[str]]:
    """Word tokens of each sentence, from the segmenter."""
    return {s: [t for t in segment_text(s) if t != "\n"] for s in sentences}


def practice(db: Session, user_id: int, point_id: str, rng: random.Random | None = None) -> dict:
    """A round of gap and word-order exercises, from the user's read texts
    first, then their other texts, then the library, then the catalog's
    own examples."""
    rng = rng or random.Random()
    e = grammar_catalog.get(point_id)
    detail = point_detail(db, user_id, point_id) if e else None
    if e is None or detail is None:
        return {"items": []}
    pool = (
        detail["sentences"]["read"] + detail["sentences"]["saved"] + detail["sentences"]["library"]
    )
    pool += [
        {
            "sentence": x["zh"],
            "span": x["zh"],
            "translation": x["en"],
            "source_title": "Example",
            "source_key": "",
            "read": False,
        }
        for x in e.get("examples") or []
    ]
    hits = [
        Hit(
            e["id"],
            s["sentence"],
            s["span"],
            s["translation"],
            s["source_key"],
            s["source_title"],
            s["read"],
        )
        for s in pool[:40]
    ]
    words_of = _words_by_sentence([h.sentence for h in hits])
    items: list[dict] = []
    for i, h in enumerate(hits):
        item = _order(h, words_of, rng) if i % 2 else _cloze(e, h, rng)
        item = item or _cloze(e, h, rng) or _order(h, words_of, rng)
        if item:
            items.append(item)
        if len(items) >= PRACTICE_ITEMS:
            break
    return {"point": grammar_catalog.summary(e), "items": items}


def record(
    db: Session, user_id: int, point_id: str, correct: int, total: int, now: datetime | None = None
) -> dict:
    """Store a practice round; a good round moves the next one further out."""
    now = now or datetime.utcnow()
    e = grammar_catalog.get(point_id)
    point = e["id"] if e else point_id
    rows = db.query(GrammarProgress).filter(GrammarProgress.user_id == user_id).all()
    row = next(
        (r for r in rows if grammar_catalog.REGEX_POINT.get(r.pattern_id, r.pattern_id) == point),
        None,
    )
    good = total > 0 and correct / total >= GOOD_ROUND
    if row is None:
        row = GrammarProgress(user_id=user_id, pattern_id=point, box=0, correct=0, total=0)
        db.add(row)
        box = 1 if good else 0
    else:
        row.pattern_id = point
        box = min(len(INTERVALS) - 1, (row.box or 0) + 1) if good else max(0, (row.box or 0) - 1)
    row.box = box
    row.correct = (row.correct or 0) + correct
    row.total = (row.total or 0) + total
    row.last_at = now
    row.due_at = now + timedelta(days=INTERVALS[box])
    db.commit()
    return _progress_payload(row, now) or {}


__all__ = ["all_hits", "overview", "point_detail", "practice", "queue_for_tagging", "record"]
