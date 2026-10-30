"""Placement test: which HSK level a new learner reads at.

Each round asks the meaning of a few words of one level (new HSK 1-6, and
7 for 7-9), four choices each: the right meaning and three meanings of
other words of the same level. The SPA moves up a level after a good
round and stops after a poor one (utils/placement.ts); `finish` then marks
the words of the levels the learner passed as known.
"""

from __future__ import annotations

import random
import re

from app.services.levels import level_number
from app.state import hsk_vocab

LEVELS = range(1, 8)  # 7 = HSK 7-9
CHOICES = 4
MAX_ITEMS = 12
_SPLIT = re.compile(r"[;,，；/(（]")


def short_meaning(meaning: str) -> str:
    """First sense, without notes: "to rest; to stop" -> "to rest"."""
    head = _SPLIT.split(meaning or "", 1)[0].strip()
    return head[:40]


def _pool(level: int) -> list[tuple[str, str, str]]:
    out = []
    for word, entry in hsk_vocab.items():
        if level_number(entry.get("level_new")) != level or not 1 <= len(word) <= 4:
            continue
        meaning = short_meaning(entry.get("meaning") or "")
        if len(meaning) >= 2 and not meaning.startswith(("(", "variant", "used in")):
            out.append((word, entry.get("pinyin") or "", meaning))
    return out


def items(level: int, n: int, exclude: set[str], rng: random.Random | None = None) -> list[dict]:
    """`n` questions at one level, none of the words in `exclude`."""
    rng = rng or random.Random()
    pool = _pool(level)
    candidates = [p for p in pool if p[0] not in exclude]
    rng.shuffle(candidates)
    out: list[dict] = []
    for word, pinyin, meaning in candidates[:n]:
        others = [m for w, _p, m in pool if w != word and m.lower() != meaning.lower()]
        wrong: list[str] = []
        for m in rng.sample(others, min(len(others), 30)):
            if m.lower() not in {x.lower() for x in wrong} and len(wrong) < CHOICES - 1:
                wrong.append(m)
        if len(wrong) < CHOICES - 1:
            continue
        choices = [meaning, *wrong]
        rng.shuffle(choices)
        out.append(
            {
                "word": word,
                "pinyin": pinyin,
                "level": level,
                "choices": choices,
                "answer": choices.index(meaning),
            }
        )
    return out


__all__ = ["LEVELS", "MAX_ITEMS", "items", "short_meaning"]
