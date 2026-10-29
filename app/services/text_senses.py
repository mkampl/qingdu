"""What the words of a text mean in it, by the LLM, for "Pre-learn words".

The dictionary's headline is the everyday meaning; in a Daoist text 大道 is
"the Great Dao", not "main street". For the words a learner picks to
pre-learn, the model gets each word's sentence (and the book's translation
of that sentence, when the text has one) and gives a short gloss for this
use. One request covers all the words of a pre-learn. Answers are cached
per word and sentence.
"""

from __future__ import annotations

from collections import OrderedDict

from app.services import llm
from app.services.text_series import plain
from app.state import cedict_vocab, hsk_vocab

FEATURE = "text_sense"
MAX_ITEMS = 40
_CACHE_SIZE = 5000
_cache: OrderedDict[tuple[str, str], str] = OrderedDict()

SCHEMA = {
    "type": "object",
    "properties": {
        "senses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"n": {"type": "integer"}, "meaning": {"type": "string"}},
                "required": ["n", "meaning"],
            },
        }
    },
    "required": ["senses"],
}

PROMPT = """A learner of Chinese is about to read a text and pre-learns some of its words.
For each word, say what it means in its sentence, as a short English gloss (1-6 words) that a
learner can put on a flash card. Where the text uses a word in a special sense (a Daoist or
Buddhist term, a name, a classical use), give that sense, not the everyday one. The book's
English translation of the sentence, when given, shows how the text means it.

{items}

Answer with one entry per number.
"""


def _dictionary(word: str) -> str:
    entry = hsk_vocab.get(word) or cedict_vocab.get(word) or {}
    return entry.get("meaning") or ""


def _item(n: int, word: str, sentence: str, translation: str | None) -> str:
    lines = [f"{n}. 「{word}」 in: {sentence}"]
    if translation:
        lines.append(f"   book translation: {translation}")
    if d := _dictionary(word):
        lines.append(f"   dictionary headline: {d}")
    return "\n".join(lines)


async def senses_in(items: list[tuple[str, str, str | None]]) -> dict[str, str]:
    """{word: meaning in its sentence} for (word, sentence, translation)
    items; words the model gave nothing for are left out."""
    out: dict[str, str] = {}
    ask: list[tuple[str, str, str | None]] = []
    for word, sentence, translation in items[:MAX_ITEMS]:
        hit = _cache.get((word, sentence))
        if hit is not None:
            _cache.move_to_end((word, sentence))
            out[word] = hit
        elif word in sentence:
            ask.append((word, sentence, translation))
    if not ask:
        return out
    reply = await llm.chat(
        [
            {
                "role": "user",
                "content": PROMPT.format(
                    items="\n".join(_item(i, *it) for i, it in enumerate(ask, 1))
                ),
            }
        ],
        schema=SCHEMA,
        max_tokens=60 + 40 * len(ask),
        temperature=0.1,
    )
    for s in reply.get("senses") or [] if isinstance(reply, dict) else []:
        n = s.get("n") if isinstance(s, dict) else None
        if not isinstance(n, int) or not 1 <= n <= len(ask):
            continue
        meaning = plain(str(s.get("meaning") or "")).strip()[:120]
        if not meaning:
            continue
        word, sentence, _ = ask[n - 1]
        out[word] = meaning
        _cache[(word, sentence)] = meaning
        if len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return out


def cached_only(items: list[tuple[str, str, str | None]]) -> bool:
    """Whether every item is answered from the cache (no LLM request, so
    nothing to charge)."""
    return all((w, s) in _cache for w, s, _ in items[:MAX_ITEMS])


__all__ = ["FEATURE", "MAX_ITEMS", "cached_only", "senses_in"]
