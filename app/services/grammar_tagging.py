"""Grammar points of a sentence, as the LLM sees them.

For each sentence the catalog offers the points whose words occur in it
(grammar_catalog.candidates); the LLM says which of those the sentence
really uses and where. The answer is checked (only offered points, the
span must be in the sentence) and stored per sentence and catalog version
(`grammar_sentence_tags`), so a sentence is looked at once, whoever reads
it. Sentences are queued when the user opens the grammar section and when
a text is read to the end; a background task works through the queue
while the LLM is available. Without an LLM nothing is queued and the
grammar section uses the reader's regex patterns only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
from collections import OrderedDict
from datetime import datetime

from app.database import GrammarSentenceTag, SessionLocal
from app.services import grammar_catalog, llm

logger = logging.getLogger(__name__)

FEATURE = "grammar"
BATCH = 6
IDLE_S = 5
MAX_QUEUE = 5000
# Bumped when the checks or the prompt change: stored tags of an older
# round are done again (they are stored as catalog version * 100 + this).
RULES = 2

_queue: OrderedDict[str, str] = OrderedDict()  # hash -> sentence
_lock = threading.Lock()

SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"id": {"type": "string"}, "span": {"type": "string"}},
                            "required": ["id", "span"],
                        },
                    },
                },
                "required": ["n", "points"],
            },
        }
    },
    "required": ["sentences"],
}

PROMPT = """You annotate Chinese sentences for learners with points of the HSK 3.0 grammar syllabus.
For each sentence below, choose from ITS candidate points only those the sentence really uses
in that grammatical function (a word that only looks the same does not count: 得 in 觉得 is not
the 得 complement, classical 得之 means "obtain"). For each chosen point give the exact span of
the sentence that shows it, including the point's grammar word. Choose nothing when no candidate
fits. Common mix-ups:
- 了 right after a verb (before its object) is 了1; 了 ending the sentence is 了2. One 了 is
  either, except a verb + 了 at the very end, which can be both.
- 在 is the preposition only before a place or time followed by the main verb (在家吃饭); in
  他在家 / 在哪儿 it is the verb; before a verb alone it marks the progressive.
- 来/去/上/下 as the main verb (去邮局) are not directional complements; a complement follows
  another verb (走进去, 拿出来).
- A character inside a longer word is not the point: 下 in 下午, 全 in 全班, 有 in 没有.
- 吧1 is a suggestion or request, 吧2 a guess or agreement; choose one.

{items}
"""


def sentence_hash(sentence: str) -> str:
    return hashlib.sha1(sentence.encode("utf-8")).hexdigest()


def tags_version() -> int:
    return grammar_catalog.version() * 100 + RULES


def span_fits(point_id: str, span: str, sentence: str) -> bool:
    """Whether a tag's span is in the sentence and holds one of the point's
    words (a 了2 tag on a clause without 了 is a guess). Whether the word
    is the grammar word there (下 in 下午) is the model's call: the reader's
    segmentation glues too much (一个, 这种, 学会) to decide it here."""
    if not span or span not in sentence:
        return False
    e = grammar_catalog.by_id().get(point_id)
    if e is None:
        return False
    markers = e.get("markers") or []
    return not markers or any(m in span for m in markers)


def enabled() -> bool:
    return llm.enabled(FEATURE) and bool(grammar_catalog.entries())


def known(hashes: list[str]) -> dict[str, list[dict]]:
    """Stored tags for these sentences (current catalog version)."""
    if not hashes:
        return {}
    out: dict[str, list[dict]] = {}
    db = SessionLocal()
    try:
        version = tags_version()
        for i in range(0, len(hashes), 500):
            for row in db.query(GrammarSentenceTag).filter(
                GrammarSentenceTag.sentence_hash.in_(hashes[i : i + 500]),
                GrammarSentenceTag.catalog_version == version,
            ):
                try:
                    out[row.sentence_hash] = json.loads(row.tags or "[]")
                except ValueError:
                    out[row.sentence_hash] = []
    finally:
        db.close()
    return out


def enqueue(sentences: list[str]) -> int:
    """Queue sentences that have candidates and no stored tags. Returns how
    many are waiting."""
    if not enabled():
        return 0
    fresh = {sentence_hash(s): s for s in dict.fromkeys(sentences) if grammar_catalog.candidates(s)}
    have = known(list(fresh))
    with _lock:
        for h, s in fresh.items():
            if h not in have and h not in _queue and len(_queue) < MAX_QUEUE:
                _queue[h] = s
        return len(_queue)


def pending() -> int:
    with _lock:
        return len(_queue)


def _take(n: int) -> list[tuple[str, str]]:
    with _lock:
        items = []
        while _queue and len(items) < n:
            items.append(_queue.popitem(last=False))
        return items


def _items_prompt(batch: list[tuple[str, str]]) -> tuple[str, list[set[str]]]:
    lines, allowed = [], []
    for n, (_h, sentence) in enumerate(batch, 1):
        cands = grammar_catalog.candidates(sentence)
        allowed.append({c["id"] for c in cands})
        lines.append(f"[{n}] {sentence}")
        for c in cands:
            lines.append(f"    {c['id']}: {c['forms']} ({c['title_en']}; {c['structure']})")
    return "\n".join(lines), allowed


async def tag_batch(batch: list[tuple[str, str]]) -> dict[str, list[dict]]:
    """Ask the LLM about a few sentences; checked tags by sentence hash."""
    items, allowed = _items_prompt(batch)
    reply = await llm.chat(
        [{"role": "user", "content": PROMPT.format(items=items)}],
        schema=SCHEMA,
        max_tokens=1500,
        temperature=0,
    )
    out: dict[str, list[dict]] = {h: [] for h, _ in batch}
    for s in reply.get("sentences", []) if isinstance(reply, dict) else []:
        n = s.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(batch):
            continue
        h, sentence = batch[n - 1]
        tags = []
        for p in s.get("points") or []:
            pid, span = str(p.get("id", "")), str(p.get("span", "")).strip()
            fits = pid in allowed[n - 1] and span_fits(pid, span, sentence)
            if fits and not any(t["id"] == pid for t in tags):
                tags.append({"id": pid, "span": span})
        out[h] = tags
    return out


def _store(results: dict[str, list[dict]], model: str | None) -> None:
    db = SessionLocal()
    try:
        version = tags_version()
        for h, tags in results.items():
            row = db.get(GrammarSentenceTag, h)
            if row is None:
                row = GrammarSentenceTag(sentence_hash=h)
                db.add(row)
            row.catalog_version = version
            row.tags = json.dumps(tags, ensure_ascii=False)
            row.model = model
            row.created_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


async def worker() -> None:
    """Background loop: tag queued sentences while the LLM is up."""
    while True:
        batch = _take(BATCH) if enabled() else []
        if not batch:
            await asyncio.sleep(IDLE_S)
            continue
        try:
            results = await tag_batch(batch)
            cfg = llm.config()
            _store(results, cfg.model if cfg else None)
        except llm.LlmError as e:
            logger.warning("Grammar tagging paused: %s", e)
            with _lock:  # put them back for the next round
                for h, s in batch:
                    _queue.setdefault(h, s)
            await asyncio.sleep(60)
        except Exception:
            logger.exception("Grammar tagging failed for a batch")


__all__ = ["enabled", "enqueue", "known", "pending", "sentence_hash", "tag_batch", "worker"]
