"""What a word means in the sentence it was clicked in, by the LLM.

The dictionary gives every sense of a word (and every reading of a
polyphone); the reader shows the headline. Here the model gets the
sentence and the dictionary's senses and says which one is meant, with a
short English gloss for this use. The reading it names must be one of the
dictionary's, and the sense number one of the listed senses; otherwise
they are left out. Answers are cached per word and sentence.
"""

from __future__ import annotations

from collections import OrderedDict

from app.services import llm
from app.services.readings import match_strength, numbered_syllables
from app.services.text_series import plain
from app.state import cedict_vocab, hsk_vocab

FEATURE = "word_sense"
MAX_SENSES = 24
_CACHE_SIZE = 2000
_cache: OrderedDict[tuple[str, ...], dict] = OrderedDict()

SCHEMA = {
    "type": "object",
    "properties": {
        "meaning": {"type": "string"},
        "sense": {"type": "integer"},
        "pinyin": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["meaning", "sense", "pinyin"],
}

PROMPT = """A learner of Chinese clicked the word 「{word}」 in this sentence:
{sentence}

The senses of {word} (a sense from the learner's word list is the meaning their school or
textbook uses; prefer it when the text is of that kind):
{senses}

1. meaning: what {word} means in this sentence, as a short English gloss (2-8 words).
2. sense: the number of the dictionary sense that is meant, or 0 when none fits.
3. pinyin: the reading of {word} here, with tone marks.
4. note: one short sentence on why, only when the sense is not the obvious one (else "").
"""


def senses(word: str, extra: list[str] | None = None) -> list[dict]:
    """[{pinyin, meaning}] for every sense in the dictionary, main reading
    first, then the meanings the user's lists give the word (a school's
    glossary: 自然 "Zì Rán, the so-of-itself")."""
    entry = hsk_vocab.get(word) or cedict_vocab.get(word) or {}
    out: list[dict] = []
    readings = entry.get("readings") or []
    if readings:
        ordered = sorted(readings, key=lambda r: not r.get("is_main"))
        for r in ordered:
            for m in r.get("meanings") or [r.get("primary") or ""]:
                if m:
                    out.append({"pinyin": r.get("pinyin") or "", "meaning": m})
    else:
        for m in entry.get("meanings") or [entry.get("meaning") or ""]:
            if m:
                out.append({"pinyin": entry.get("pinyin") or "", "meaning": m})
    out = out[:MAX_SENSES]
    seen = {s["meaning"] for s in out}
    for m in extra or []:
        if m and m not in seen:
            out.append({"pinyin": entry.get("pinyin") or "", "meaning": m, "list": True})
            seen.add(m)
    return out


async def sense_in(word: str, sentence: str, extra: list[str] | None = None) -> dict:
    word, sentence = word.strip(), sentence.strip()
    extra = [m.strip()[:200] for m in (extra or [])[:5] if m and m.strip()]
    key = (word, sentence, *extra)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached
    listed = senses(word, extra)
    reply = await llm.chat(
        [
            {
                "role": "user",
                "content": PROMPT.format(
                    word=word,
                    sentence=sentence,
                    senses="\n".join(
                        f"{i}. ({s['pinyin']}) {s['meaning']}"
                        + (" [from the learner's word list]" if s.get("list") else "")
                        for i, s in enumerate(listed, 1)
                    )
                    or "(none: the dictionary does not list this word)",
                ),
            }
        ],
        schema=SCHEMA,
        max_tokens=300,
        temperature=0.1,
    )
    meaning = plain(str(reply.get("meaning") or ""))[:120]
    if not meaning:
        raise llm.LlmError("The model gave no meaning")
    number = reply.get("sense")
    matched = listed[number - 1] if isinstance(number, int) and 1 <= number <= len(listed) else None
    pinyin = plain(str(reply.get("pinyin") or ""))
    wanted = numbered_syllables(pinyin)
    # Only a reading the dictionary has (compared as syllables with tones;
    # a neutral tone on one side still matches).
    strength = {
        p: match_strength(wanted, numbered_syllables(p)) for p in {s["pinyin"] for s in listed}
    }
    best = max(strength, key=strength.get, default=None)
    pinyin = best if best and strength[best] > 0 else (matched["pinyin"] if matched else None)
    out = {
        "word": word,
        "meaning": meaning,
        "pinyin": pinyin,
        "dictionary_sense": matched["meaning"] if matched else None,
        "note": plain(str(reply.get("note") or ""))[:240] or None,
    }
    _cache[key] = out
    if len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return out


__all__ = ["FEATURE", "sense_in", "senses"]
