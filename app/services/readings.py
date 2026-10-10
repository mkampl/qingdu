"""
Readings of polyphone headwords (好 hǎo/hào, 长 cháng/zhǎng, 东西
dōng xi/dōng xī).

CC-CEDICT lists each reading of a headword on its own line. The loader
keeps all of them (`entry["readings"]`); this module decides which one is
the *main* reading of an HSK word and builds the "other readings" payload
the reader popover and the review card show under the main gloss.

Main reading of an HSK word: the CC-CEDICT reading that matches both the
HSK-list pinyin and pypinyin's phrase-aware reading. When the two
disagree, the better-scored of the readings that match either one wins
(`cedict_loader._entry_quality`), and when neither matches anything the
scorer's own pick stays. `app/data/reading_overrides.json` pins the
handful of words where that still goes wrong; the HSK list's pinyin is
just its first CC-CEDICT form, so it is often the rare reading (个 gě,
读 dòu, 听 yǐn).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

from pypinyin import Style, pinyin

logger = logging.getLogger(__name__)

READING_OVERRIDES_FILE = Path(__file__).resolve().parent.parent / "data" / "reading_overrides.json"

_TONE_OF_MARK = {"̄": 1, "́": 2, "̌": 3, "̀": 4}
_SYLLABLE_RE = re.compile(r"^[a-zv]+$")

# A strong match is the same syllables with the same tones; a weak one
# differs only where one side has the neutral tone (东西 dōng xi in a
# textbook, dōng xī from pypinyin).
NO_MATCH, WEAK_MATCH, STRONG_MATCH = 0, 1, 2


def numbered_syllables(text: str | None) -> tuple[str, ...] | None:
    """Pinyin as lower-case numbered syllables, neutral tone 5, ü as v
    and erhua as a separate "r5": "dōng xi" → ("dong1", "xi5"),
    "yī huìr" → ("yi1", "hui4", "r5"), "nu:3 hai2" → ("nv3", "hai2").
    Takes tone marks or tone numbers. None when the text isn't
    space-separated pinyin (the HSK list has a few run-together forms)."""
    if not text or not text.strip():
        return None
    out: list[str] = []
    for token in text.strip().lower().split():
        token = token.replace("u:", "v")
        if token[-1].isdigit():
            base, tone = token[:-1], int(token[-1])
        else:
            tone = 5
            base_chars = []
            for ch in unicodedata.normalize("NFD", token):
                if ch in _TONE_OF_MARK:
                    tone = _TONE_OF_MARK[ch]
                elif ch == "̈":  # combining diaeresis: ü
                    if base_chars and base_chars[-1] == "u":
                        base_chars[-1] = "v"
                else:
                    base_chars.append(ch)
            base = "".join(base_chars)
        base = base.replace("ü", "v")
        if tone == 0 or tone > 5:
            tone = 5
        if not _SYLLABLE_RE.match(base):
            return None
        if base.endswith("r") and base not in ("r", "er") and not token[-1].isdigit():
            out.extend((f"{base[:-1]}{tone}", "r5"))
        else:
            out.append(f"{base}{tone}")
    return tuple(out)


def phrase_reading(word: str) -> tuple[str, ...] | None:
    """pypinyin's reading of `word`, using its phrase dictionary so 好吃
    is hǎo chī and 当时 dāng shí. A final 儿 after another character is
    read as erhua, the way CC-CEDICT writes it."""
    syllables = [s[0] for s in pinyin(word, style=Style.TONE3, neutral_tone_with_five=True)]
    if len(syllables) != len(word) or not all(_SYLLABLE_RE.match(s[:-1] or "?") for s in syllables):
        return None
    if len(word) > 1 and word.endswith("儿") and syllables[-1].startswith("er"):
        syllables[-1] = "r5"
    return numbered_syllables(" ".join(syllables))


def match_strength(a: tuple[str, ...] | None, b: tuple[str, ...] | None) -> int:
    if not a or not b or len(a) != len(b):
        return NO_MATCH
    if a == b:
        return STRONG_MATCH
    for x, y in zip(a, b, strict=True):
        if x[:-1] != y[:-1]:
            return NO_MATCH
        if x[-1] != y[-1] and "5" not in (x[-1], y[-1]):
            return NO_MATCH
    return WEAK_MATCH


def _matching(
    target: tuple[str, ...] | None,
    candidates: list[tuple[str, ...] | None],
    strong_first: bool = False,
) -> list[int]:
    """Indices of the candidates matching `target`, neutral tones aside.
    With `strong_first`, only the exact matches when there are any."""
    strengths = [match_strength(target, c) for c in candidates]
    if strong_first and STRONG_MATCH in strengths:
        return [i for i, s in enumerate(strengths) if s == STRONG_MATCH]
    return [i for i, s in enumerate(strengths) if s != NO_MATCH]


def _neutral_preference(word: str, syllables: tuple[str, ...] | None, is_stub: bool) -> int:
    """For a compound, the reading with more neutral-tone syllables is
    usually the everyday word: 东西 dōng xi "thing" vs dōng xī "east and
    west", 告诉 gào su "to tell" vs gào sù "to press charges", 故事 gù shi
    "story" vs gù shì "old practice". Ranked last: a reading with no full
    tone at all, which is a grammatical complement (起来 qi lai after a
    verb), and a stub that only points elsewhere or names a function
    (过来 guò lai "see 过来 guò lái", 过去 guò qu "(verb suffix)").
    Single characters score 0: 哪 na (particle) must not beat nǎ."""
    if len(word) < 2 or not syllables:
        return 0
    if is_stub:
        return -2
    neutral = sum(1 for s in syllables if s.endswith("5"))
    return -1 if neutral == len(syllables) else neutral


def pick_main_reading(
    word: str,
    candidates: list[tuple[str, int, bool]],
    hsk_pinyin: str | None,
    override: str | None = None,
) -> int | None:
    """Index of the main reading among `candidates` ((numbered pinyin,
    quality score, is_stub) per CC-CEDICT reading, in file order), or
    None to keep the scorer's pick.

    - An override (tone-marked pinyin) wins when CC-CEDICT has it.
    - Otherwise the best-scored reading that matches the HSK-list pinyin
      or pypinyin's phrase reading. When the two agree that is a single
      reading; when they disagree the scorer decides between them.
    - Neutral tones: neither source marks them reliably (both give 告诉
      gào sù and 东西 dōng xī), so the matches include readings that
      differ only there, and for a compound the neutral-tone reading
      ranks first (see _neutral_preference).
    - Stubs (pointers, readings that only occur inside one compound)
      never anchor: pypinyin's default for 似 is shì, which CC-CEDICT
      has only as "used in 似的", so 似 keeps the scorer's sì.
    - HSK component characters carry no list pinyin; pypinyin alone
      anchors them.
    """
    syllables = [numbered_syllables(c[0]) for c in candidates]

    def best_of(indices) -> int | None:
        indices = list(indices)
        if not indices:
            return None
        return max(
            indices,
            key=lambda i: (
                _neutral_preference(word, syllables[i], candidates[i][2]),
                candidates[i][1],
                # Same as the scorer: on a tie the later CC-CEDICT line wins.
                i,
            ),
        )

    if override:
        pinned = best_of(_matching(numbered_syllables(override), syllables, strong_first=True))
        if pinned is not None:
            return pinned
        logger.warning("Reading override %s %s matches no CC-CEDICT reading", word, override)

    pool: set[int] = set()
    for anchor in (numbered_syllables(hsk_pinyin), phrase_reading(word)):
        pool.update(_matching(anchor, syllables))
    return best_of(i for i in pool if not candidates[i][2])


def load_reading_overrides(path: Path | None = None) -> dict[str, str]:
    """{word: tone-marked pinyin} from app/data/reading_overrides.json.
    Missing or broken file → {} (anchoring still runs, just unpinned)."""
    path = path or READING_OVERRIDES_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for word, item in (data.get("readings") or {}).items():
        reading = item.get("pinyin") if isinstance(item, dict) else item
        if isinstance(reading, str) and reading.strip():
            out[word] = reading.strip()
    return out


# --- usage examples for the other readings -------------------------------------


def _level_rank(entry: dict) -> int:
    for key in ("level_new", "level_old"):
        m = re.match(r"(?:new|old)-(\d+)", entry.get(key) or "")
        if m:
            return int(m.group(1))
    return 99


def build_example_index(
    parsed: dict[str, dict], vocab: dict[str, dict]
) -> dict[tuple[str, str], str]:
    """(character, numbered syllable) → the most basic HSK word that
    reads the character that way: lowest HSK level, then the list's
    frequency rank (lower = more common), then the shorter word.
    长 zhang3 → 校长; 长 chang2 → 长城 or similar."""
    best: dict[tuple[str, str], tuple] = {}
    for word, hsk_entry in vocab.items():
        if len(word) < 2 or not hsk_entry.get("is_original_hsk"):
            continue
        entry = parsed.get(word)
        if not entry:
            continue
        syllables = numbered_syllables(entry.get("numbered_pinyin") or entry.get("pinyin"))
        if not syllables or len(syllables) != len(word):
            continue
        rank = (
            _level_rank(hsk_entry),
            hsk_entry.get("frequency") or 10**9,
            len(word),
            word,
        )
        for char, syllable in zip(word, syllables, strict=True):
            key = (char, syllable)
            if key not in best or rank < best[key]:
                best[key] = rank
    return {key: rank[-1] for key, rank in best.items()}


# --- API payload ------------------------------------------------------------------


def readings_payload(entry: dict | None, main_pinyin: str | None = None) -> list[dict] | None:
    """The `readings` list for API responses: [{pinyin, primary, meanings,
    meaning_tags, is_main, example}], main reading first. None when the
    word has a single reading, so most tokens carry nothing extra.

    `main_pinyin` marks a different reading as main when it matches one,
    e.g. a review card whose stored pinyin is not the dictionary's main
    reading."""
    readings = (entry or {}).get("readings") or []
    if len(readings) < 2:
        return None
    main_index = next((i for i, r in enumerate(readings) if r.get("is_main")), 0)
    wanted = numbered_syllables(main_pinyin)
    if wanted:
        for i, r in enumerate(readings):
            if match_strength(wanted, numbered_syllables(r.get("pinyin"))) == STRONG_MATCH:
                main_index = i
                break
    out = []
    for i, r in enumerate(readings):
        out.append(
            {
                "pinyin": r.get("pinyin", ""),
                "primary": r.get("primary", ""),
                "meanings": list(r.get("meanings") or []),
                "meaning_tags": list(r.get("meaning_tags") or []),
                "is_main": i == main_index,
                "example": dict(r["example"]) if r.get("example") and i != main_index else None,
            }
        )
    out.sort(key=lambda r: not r["is_main"])
    return out


__all__ = [
    "build_example_index",
    "load_reading_overrides",
    "match_strength",
    "numbered_syllables",
    "phrase_reading",
    "pick_main_reading",
    "readings_payload",
]
