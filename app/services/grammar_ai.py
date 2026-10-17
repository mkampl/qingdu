"""LLM help with grammar: explain one sentence, write a practice text.

- explain(): which catalog points a sentence uses (chosen from the points
  whose words occur in it, spans checked), a short breakdown of how it is
  built, and a word-by-word gloss. Cached per sentence.
- practice_text(): a short text at the point's level that uses the point
  several times and mostly words the user knows; it is checked (the
  point's words occur, the user can read most of it) and written again
  once when it falls short.
"""

from __future__ import annotations

from collections import OrderedDict

from sqlalchemy.orm import Session

from app.database import UserWord
from app.services import grammar_catalog, llm, readability
from app.services.segmentation import segment_text
from app.state import hsk_vocab

EXPLAIN = "explain_sentence"
PRACTICE = "practice_text"
MIN_KNOWN = 0.8
_explained: OrderedDict[str, dict] = OrderedDict()
_EXPLAIN_CACHE = 500

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "span": {"type": "string"}},
                "required": ["id", "span"],
            },
        },
        "breakdown": {"type": "string"},
        "literal": {"type": "string"},
    },
    "required": ["points", "breakdown", "literal"],
}

EXPLAIN_PROMPT = """Explain the grammar of this Chinese sentence to a learner, in English.
Sentence: {sentence}

1. points: which of these candidate grammar points the sentence really uses (a word that only
   looks the same does not count), each with the exact span of the sentence that shows it:
{candidates}
2. breakdown: 2-4 short sentences on how the sentence is built (subject, verb, what each
   grammar word does), for a learner.
3. literal: a word-by-word English gloss in the sentence's order.
"""

TEXT_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "text": {"type": "string"}},
    "required": ["title", "text"],
}

TEXT_PROMPT = """Write a short Chinese text (6-9 sentences, about {chars} characters, simplified
characters) at HSK {level} level that uses this grammar point at least three times, naturally:
{forms} — {title} ({structure})
Topic: everyday life. Use mainly these words the reader knows: {words}
Give it a short Chinese title. Plain text, no pinyin, no English.{stricter}
"""


def _known_words(db: Session, user_id: int, max_level: int, limit: int = 150) -> list[str]:
    """Words the user knows at or below the level, most frequent first, so
    the text is built from everyday words they can read."""
    known = {
        w
        for (w,) in db.query(UserWord.word).filter(
            UserWord.user_id == user_id, UserWord.state == "known"
        )
    }

    def level(word: str) -> int:
        raw = str((hsk_vocab.get(word) or {}).get("level_new") or "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        return int(digits) if digits else 99

    pool = [w for w in known if level(w) <= max(max_level, 2)]
    pool.sort(key=lambda w: -int((hsk_vocab.get(w) or {}).get("frequency") or 0))
    return pool[:limit]


async def explain(sentence: str) -> dict:
    sentence = sentence.strip()
    cached = _explained.get(sentence)
    if cached is not None:
        _explained.move_to_end(sentence)
        return cached
    cands = grammar_catalog.candidates(sentence)
    listing = (
        "\n".join(f"   {c['id']}: {c['forms']} ({c['title_en']})" for c in cands) or "   (none)"
    )
    reply = await llm.chat(
        [
            {
                "role": "user",
                "content": EXPLAIN_PROMPT.format(sentence=sentence, candidates=listing),
            }
        ],
        schema=EXPLAIN_SCHEMA,
        max_tokens=900,
        temperature=0.2,
    )
    allowed = {c["id"] for c in cands}
    points = []
    for p in reply.get("points") or []:
        pid, span = str(p.get("id", "")), str(p.get("span", "")).strip()
        if pid in allowed and span and span in sentence and pid not in {x["id"] for x in points}:
            e = grammar_catalog.by_id()[pid]
            points.append({"id": pid, "span": span, "title": e["title_en"], "level": e["level"]})
    out = {
        "sentence": sentence,
        "points": points,
        "breakdown": str(reply.get("breakdown") or "").strip(),
        "literal": str(reply.get("literal") or "").strip(),
    }
    _explained[sentence] = out
    if len(_explained) > _EXPLAIN_CACHE:
        _explained.popitem(last=False)
    return out


def _level_number(level: str) -> int:
    return 7 if level == "7-9" else int(level)


async def practice_text(db: Session, user_id: int, point_id: str) -> dict:
    e = grammar_catalog.get(point_id)
    if e is None:
        raise llm.LlmError("Unknown grammar point")
    level = _level_number(e["level"])
    words = _known_words(db, user_id, level)
    best: dict | None = None
    for attempt in range(2):
        reply = await llm.chat(
            [
                {
                    "role": "user",
                    "content": TEXT_PROMPT.format(
                        chars=120 + 30 * level,
                        level=e["level"],
                        forms=e["forms"],
                        title=e["title_en"],
                        structure=e["structure"],
                        words="、".join(words) or "(any HSK 1-2 words)",
                        stricter=(
                            "\nUse only very common words; the last text was too hard."
                            if attempt
                            else ""
                        ),
                    ),
                }
            ],
            schema=TEXT_SCHEMA,
            max_tokens=1200,
            temperature=0.7,
        )
        text = str(reply.get("text") or "").strip()
        title = str(reply.get("title") or "").strip()[:60] or e["title_en"]
        uses = sum(text.count(m) for m in e.get("markers") or [])
        if not text or (e.get("markers") and uses < 2):
            continue
        tokens = segment_text(text)
        summary = readability.for_user(db, user_id, tokens)
        candidate = {
            "title": title,
            "text": text,
            "known_pct": round(summary.known_pct, 3),
            "point": grammar_catalog.summary(e),
        }
        if best is None or candidate["known_pct"] > best["known_pct"]:
            best = candidate
        if summary.with_progress_pct >= MIN_KNOWN:
            break
    if best is None:
        raise llm.LlmError("The model's text did not use the grammar point")
    return best


__all__ = ["EXPLAIN", "PRACTICE", "explain", "practice_text"]
