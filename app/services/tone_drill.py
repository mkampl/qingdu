"""Tone practice: hear a word, pick its tones.

Each item is a word the user is learning or knows (topped up with
everyday HSK words), played as audio, with up to four pinyin choices that
differ only in tone. Real minimal pairs come first, written with their
hanzi (买 mǎi / 卖 mài); made-up tone variants fill the rest.

Left out: words with a neutral tone or erhua, and words whose spoken
tones differ from the dictionary's (一 and 不, two third tones in a row),
so the audio always matches the right answer. Practice only: nothing is
graded into the review schedule.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database import UserWord
from app.services.cedict_loader import _apply_tone
from app.services.levels import level_number
from app.services.readings import numbered_syllables
from app.state import hsk_vocab

CHOICES = 4
MAX_ITEMS = 30
# Everyday HSK words used when the user's own words run short.
FALLBACK_MAX_LEVEL = 3
# Characters whose spoken tone changes with the next syllable.
SANDHI_CHARS = set("一不")


@dataclass(frozen=True)
class Candidate:
    word: str
    tones: tuple[str, ...]  # numbered syllables, e.g. ("mai3",)
    meaning: str
    level: int | None


def _tones(word: str, pinyin: str | None) -> tuple[str, ...] | None:
    syl = numbered_syllables(pinyin)
    if not syl or len(syl) != len(word) or len(word) > 2:
        return None
    if any(not s[-1:].isdigit() or s[-1] in "50" for s in syl):
        return None  # neutral tone or erhua
    if SANDHI_CHARS & set(word):
        return None
    if len(syl) == 2 and syl[0][-1] == syl[1][-1] == "3":
        return None  # spoken as 2-3
    return syl


def candidates() -> dict[str, Candidate]:
    out: dict[str, Candidate] = {}
    for word, entry in hsk_vocab.items():
        tones = _tones(word, entry.get("pinyin"))
        if tones and entry.get("meaning"):
            level = level_number(entry.get("level_new") or entry.get("level"), ("new-", "old-"))
            out[word] = Candidate(word, tones, entry["meaning"], level)
    return out


def _base(tones: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(s[:-1] for s in tones)


def marked(tones: tuple[str, ...]) -> str:
    return " ".join(_apply_tone(s) for s in tones)


def _variants(tones: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Every other tone pattern on the same syllables."""
    out: list[tuple[str, ...]] = [()]
    for syl in tones:
        out = [prev + (syl[:-1] + t,) for prev in out for t in "1234"]
    return [v for v in out if v != tones]


def choices(
    item: Candidate, by_base: dict[tuple[str, ...], list[Candidate]], rng: random.Random
) -> tuple[list[dict], int]:
    """The answer and up to three other tone patterns; real words first."""
    picked: dict[tuple[str, ...], str | None] = {item.tones: item.word}
    partners = [c for c in by_base.get(_base(item.tones), []) if c.tones != item.tones]
    rng.shuffle(partners)
    partners.sort(key=lambda c: c.level or 99)  # everyday words first
    for c in partners:
        if len(picked) >= CHOICES:
            break
        picked.setdefault(c.tones, c.word)
    rest = [v for v in _variants(item.tones) if v not in picked]
    rng.shuffle(rest)
    for v in rest[: CHOICES - len(picked)]:
        picked[v] = None
    opts = [{"pinyin": marked(t), "word": w, "_t": t} for t, w in picked.items()]
    rng.shuffle(opts)
    answer = next(i for i, o in enumerate(opts) if o["_t"] == item.tones)
    for o in opts:
        o.pop("_t")
        if o["word"] == item.word:
            o["word"] = None  # the answer's hanzi is on the card already
    return opts, answer


def build(db: Session, user_id: int, n: int, rng: random.Random | None = None) -> list[dict]:
    rng = rng or random.Random()
    pool = candidates()
    by_base: dict[tuple[str, ...], list[Candidate]] = defaultdict(list)
    for c in pool.values():
        by_base[_base(c.tones)].append(c)

    def has_pair(c: Candidate) -> bool:
        return len(by_base[_base(c.tones)]) > 1

    mine = [
        pool[w]
        for (w,) in db.query(UserWord.word).filter(
            UserWord.user_id == user_id, UserWord.state.in_(("learning", "known"))
        )
        if w in pool
    ]
    rng.shuffle(mine)
    # Words with a real minimal pair first: those are the useful contrasts.
    mine.sort(key=lambda c: not has_pair(c))
    chosen = mine[:n]
    if len(chosen) < n:
        taken = {c.word for c in chosen}
        extra = [
            c
            for c in pool.values()
            if c.word not in taken
            and has_pair(c)
            and c.level is not None
            and c.level <= FALLBACK_MAX_LEVEL
        ]
        rng.shuffle(extra)
        chosen += extra[: n - len(chosen)]
    rng.shuffle(chosen)

    items = []
    for c in chosen:
        opts, answer = choices(c, by_base, rng)
        items.append(
            {
                "word": c.word,
                "pinyin": marked(c.tones),
                "meaning": c.meaning,
                "choices": opts,
                "answer": answer,
            }
        )
    return items


__all__ = ["CHOICES", "MAX_ITEMS", "build", "candidates", "choices", "marked"]
