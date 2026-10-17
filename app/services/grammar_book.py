"""The user's grammar: which patterns they have met in what they read, the
sentences that show them, practice built from those sentences, and when
each pattern is due again.

Sources:
- texts read to the end: saved texts at 99 % reading progress, library
  texts marked read or with a passed quiz ("met" counts only these);
- the user's other saved texts and the bundled library texts, for more
  example and practice sentences.

Sentences are found with the same detector the reader uses
(services/grammar), run on each text's stored segmentation. Per-text
results are cached in memory, keyed by the analysis' length, so an
edited text is looked at again.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import GrammarProgress, SavedText, UserLibraryProgress
from app.services import grammar, library
from app.services.segmentation import _group_sentences

READ_THROUGH = 0.99
MAX_SENTENCES = 60
MAX_SENTENCE_CHARS = 80
# Days until a pattern is due again, by box (raised by a good practice
# round, lowered by a poor one).
INTERVALS = (1, 2, 4, 8, 16, 32, 64)
GOOD_ROUND = 0.8
CJK = re.compile(r"[㐀-鿿]")


@dataclass(frozen=True)
class Hit:
    pattern_id: str
    sentence: str
    span: str
    translation: str | None
    source_key: str  # "saved:<id>" | "library:<slug>"
    source_title: str
    read: bool  # from a text the user has read to the end
    level: int | None = None  # HSK level of a library text


_cache: dict[str, tuple[int, list[tuple[str, str, str, str | None]]]] = {}


def _hits_in_words(
    key: str, size: int, words: list[dict], translations: dict
) -> list[tuple[str, str, str, str | None]]:
    """(pattern_id, sentence, span, translation) for one text, cached."""
    tokens = [(w.get("text") or "") for w in words if isinstance(w, dict)]
    sentences = _group_sentences(tokens)
    matches, _metas = grammar.detect_patterns(sentences)
    out: list[tuple[str, str, str, str | None]] = []
    for m in matches:
        sentence = sentences[m.sentence_idx][1].text.strip()
        if not sentence or len(sentence) > MAX_SENTENCE_CHARS:
            continue
        out.append((m.pattern_id, sentence, m.span_text, translations.get(sentence)))
    _cache[key] = (size, out)
    return out


def _cached(key: str, size: int) -> list[tuple[str, str, str, str | None]] | None:
    hit = _cache.get(key)
    return hit[1] if hit and hit[0] == size else None


def _progress_fraction(raw) -> float:
    try:
        value = float(raw or 0)
    except (TypeError, ValueError):
        return 0.0
    return value / 100 if value > 1 else value


def _saved_hits(db: Session, user_id: int) -> list[Hit]:
    out: list[Hit] = []
    # The analysis length tells whether a text changed; only new or changed
    # texts are read and parsed.
    rows = db.query(
        SavedText.id,
        SavedText.title,
        SavedText.reading_progress,
        func.length(SavedText.analysis_data),
    ).filter(SavedText.user_id == user_id)
    for text_id, title, progress, size in rows:
        key = f"saved:{text_id}"
        hits = _cached(key, size or 0)
        if hits is None:
            raw = db.query(SavedText.analysis_data).filter(SavedText.id == text_id).scalar() or ""
            try:
                data = json.loads(raw) if raw else {}
            except ValueError:
                data = {}
            words = data.get("words") if isinstance(data, dict) else None
            if not isinstance(words, list):
                _cache[key] = (size or 0, [])
                continue
            hits = _hits_in_words(key, size or 0, words, data.get("sentence_translations") or {})
        read = _progress_fraction(progress) >= READ_THROUGH
        for pid, sentence, span, tr in hits:
            out.append(Hit(pid, sentence, span, tr, key, title or "", read))
    return out


def _library_hits(db: Session, user_id: int) -> list[Hit]:
    read = {
        slug
        for (slug,) in db.query(UserLibraryProgress.slug).filter(
            UserLibraryProgress.user_id == user_id,
            UserLibraryProgress.status.in_(("read", "quiz")),
        )
    }
    out: list[Hit] = []
    for entry in library._all_entries():
        slug = entry["slug"]
        key = f"library:{slug}"
        hits = _cached(key, 0)
        if hits is None:
            words = (entry.get("analyzed") or {}).get("words") or []
            hits = _hits_in_words(key, 0, words, {})
        for pid, sentence, span, tr in hits:
            out.append(
                Hit(pid, sentence, span, tr, key, entry["title"], slug in read, entry["hsk_level"])
            )
    return out


def all_hits(db: Session, user_id: int) -> list[Hit]:
    return _saved_hits(db, user_id) + _library_hits(db, user_id)


def _progress(db: Session, user_id: int) -> dict[str, GrammarProgress]:
    return {
        p.pattern_id: p
        for p in db.query(GrammarProgress).filter(GrammarProgress.user_id == user_id)
    }


def _progress_payload(p: GrammarProgress | None, now: datetime) -> dict | None:
    if p is None:
        return None
    return {
        "box": p.box,
        "due": p.due_at is not None and p.due_at <= now,
        "due_at": p.due_at.isoformat() + "Z" if p.due_at else None,
        "last_at": p.last_at.isoformat() + "Z" if p.last_at else None,
        "correct": p.correct,
        "total": p.total,
    }


def overview(db: Session, user_id: int, now: datetime | None = None) -> dict:
    """Every pattern with what the user has met and practised."""
    now = now or datetime.utcnow()
    hits = [h for h in all_hits(db, user_id) if h.read]
    progress = _progress(db, user_id)
    patterns = []
    for p in grammar.PATTERNS:
        mine = [h for h in hits if h.pattern_id == p.id]
        patterns.append(
            {
                **grammar.pattern_meta(p.id),
                "met_texts": len({h.source_key for h in mine}),
                "met_sentences": len({h.sentence for h in mine}),
                "progress": _progress_payload(progress.get(p.id), now),
            }
        )
    read_texts = len({h.source_key for h in hits})
    return {"patterns": patterns, "read_texts": read_texts}


def _hit_payload(h: Hit) -> dict:
    return {
        "sentence": h.sentence,
        "span": h.span,
        "translation": h.translation,
        "source_key": h.source_key,
        "source_title": h.source_title,
        "read": h.read,
    }


def pattern_detail(db: Session, user_id: int, pattern_id: str) -> dict | None:
    """A pattern with the sentences that show it: from texts the user has
    read first, then their other texts, then the library (easiest first)."""
    if pattern_id not in {p.id for p in grammar.PATTERNS}:
        return None
    meta = grammar.pattern_meta(pattern_id)
    seen: set[str] = set()
    groups: dict[str, list[dict]] = {"read": [], "saved": [], "library": []}
    hits = [h for h in all_hits(db, user_id) if h.pattern_id == pattern_id]
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
    progress = _progress(db, user_id).get(pattern_id)
    return {
        **meta,
        "sentences": groups,
        "progress": _progress_payload(progress, datetime.utcnow()),
    }


# --- Practice ------------------------------------------------------------------

# The words of each pattern that a gap exercise can blank, and words that
# are easily confused with them (the wrong choices).
MARKERS: dict[str, list[str]] = {
    "shi-de": ["是"],
    "ba": ["把"],
    "bei": ["被"],
    "yue-yue": ["越"],
    "yibian-yibian": ["一边"],
    "yinwei-suoyi": ["所以", "因为"],
    "suiran-danshi": ["但是", "虽然", "可是"],
    "budan-erqie": ["而且", "不但", "不仅"],
    "ruguo-jiu": ["如果", "要是", "就"],
    "le-aspect": ["了"],
    "cong-dao": ["从", "到"],
    "gen-yiqi": ["一起"],
    "guo-experiential": ["过"],
    "bi-comparison": ["比"],
    "zhe-durative": ["着"],
    "de-resultative": ["得"],
    "you-you": ["又"],
    "rang-jiao": ["让", "叫"],
    "gei-benefactive": ["给"],
    "jiuyao-le": ["就要", "快要"],
    "yi-jiu": ["就"],
    "gang-jiu": ["刚"],
    "chule-yiwai": ["除了", "以外"],
    "lian-ye": ["连"],
    "zhiyao-jiu": ["只要"],
    "zhiyou-cai": ["只有", "才"],
    "bushi-ershi": ["而是"],
    "yaome-yaome": ["要么"],
    "dehua-jiu": ["的话"],
    "kenenghui": ["可能"],
}
CONFUSABLE: dict[str, list[str]] = {
    "把": ["被", "给", "让"],
    "被": ["把", "给", "让"],
    "给": ["把", "被", "对"],
    "让": ["被", "把", "给"],
    "叫": ["被", "把", "给"],
    "所以": ["但是", "而且", "可是"],
    "因为": ["虽然", "如果", "只要"],
    "但是": ["所以", "而且", "因为"],
    "可是": ["所以", "而且", "因为"],
    "虽然": ["因为", "如果", "只要"],
    "而且": ["但是", "所以", "可是"],
    "不但": ["虽然", "因为", "如果"],
    "不仅": ["虽然", "因为", "如果"],
    "如果": ["因为", "虽然", "只有"],
    "要是": ["因为", "虽然", "只有"],
    "就": ["才", "都", "也"],
    "才": ["就", "都", "也"],
    "了": ["过", "着", "的"],
    "过": ["了", "着", "的"],
    "着": ["了", "过", "的"],
    "得": ["的", "地", "了"],
    "是": ["在", "有", "要"],
    "越": ["又", "也", "更"],
    "又": ["也", "越", "还"],
    "一边": ["一起", "一下", "一直"],
    "从": ["到", "在", "离"],
    "到": ["从", "在", "离"],
    "一起": ["一边", "一样", "一直"],
    "比": ["跟", "和", "像"],
    "就要": ["正在", "已经", "刚才"],
    "快要": ["正在", "已经", "刚才"],
    "刚": ["才", "就", "都"],
    "除了": ["除非", "为了", "关于"],
    "以外": ["以后", "以前", "之间"],
    "连": ["就", "才", "也"],
    "只要": ["只有", "虽然", "因为"],
    "只有": ["只要", "虽然", "因为"],
    "而是": ["但是", "所以", "而且"],
    "要么": ["或者", "还是", "不是"],
    "的话": ["以后", "时候", "以前"],
    "可能": ["应该", "一定", "已经"],
}
PRACTICE_ITEMS = 8


def _cloze(pattern_id: str, h: Hit, rng: random.Random) -> dict | None:
    for marker in MARKERS.get(pattern_id, []):
        start = h.sentence.find(h.span)
        at = h.sentence.find(marker, max(start, 0)) if start >= 0 else h.sentence.find(marker)
        if at < 0:
            continue
        wrong = [w for w in CONFUSABLE.get(marker, []) if w != marker][:3]
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
    from app.services.segmentation import segment_text

    return {s: [t for t in segment_text(s) if t != "\n"] for s in sentences}


def practice(db: Session, user_id: int, pattern_id: str, rng: random.Random | None = None) -> dict:
    """A round of gap and word-order exercises, from the user's read texts
    first, then their other texts, then the library."""
    rng = rng or random.Random()
    detail = pattern_detail(db, user_id, pattern_id)
    if detail is None:
        return {"items": []}
    pool = (
        detail["sentences"]["read"] + detail["sentences"]["saved"] + detail["sentences"]["library"]
    )
    if not pool:
        meta = grammar.pattern_meta(pattern_id)
        pool = [
            {
                "sentence": meta["example"],
                "span": meta["example"],
                "translation": meta["example_translation"],
                "source_title": "Example",
                "source_key": "",
                "read": False,
            }
        ]
    hits = [
        Hit(
            pattern_id,
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
        item = _order(h, words_of, rng) if i % 2 else _cloze(pattern_id, h, rng)
        item = item or _cloze(pattern_id, h, rng) or _order(h, words_of, rng)
        if item:
            items.append(item)
        if len(items) >= PRACTICE_ITEMS:
            break
    return {"pattern": grammar.pattern_meta(pattern_id), "items": items}


def record(
    db: Session,
    user_id: int,
    pattern_id: str,
    correct: int,
    total: int,
    now: datetime | None = None,
) -> dict:
    """Store a practice round; a good round moves the next one further out."""
    now = now or datetime.utcnow()
    row = (
        db.query(GrammarProgress)
        .filter(GrammarProgress.user_id == user_id, GrammarProgress.pattern_id == pattern_id)
        .first()
    )
    if row is None:
        row = GrammarProgress(user_id=user_id, pattern_id=pattern_id, box=0, correct=0, total=0)
        db.add(row)
        good = total > 0 and correct / total >= GOOD_ROUND
        box = 0 if not good else 1
    else:
        good = total > 0 and correct / total >= GOOD_ROUND
        box = min(len(INTERVALS) - 1, (row.box or 0) + 1) if good else max(0, (row.box or 0) - 1)
    row.box = box
    row.correct = (row.correct or 0) + correct
    row.total = (row.total or 0) + total
    row.last_at = now
    row.due_at = now + timedelta(days=INTERVALS[box])
    db.commit()
    return _progress_payload(row, now) or {}


__all__ = ["all_hits", "overview", "pattern_detail", "practice", "record"]
