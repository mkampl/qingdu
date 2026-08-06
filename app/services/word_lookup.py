"""
Word-info lookup for terms missing from the HSK vocabulary.

Three strategies, tried in this order by `app.services.segmentation`:
- `resolve_from_cedict`: a direct CC-CEDICT hit for the whole segment. Free,
  instant, and curated — wins over both strategies below whenever it applies.
- `create_compound_from_hsk`: build a compound entry from the HSK character
  components when every character of the word is known (but CEDICT has no
  entry for the word as a whole), then enrich with an online translation
  (falling back to the per-character glosses if the online result looks like
  pinyin or is too short to be useful).
- `lookup_unknown_word`: pure online translation + pypinyin fallback, for
  segments with no CEDICT entry and at least one non-HSK character.
"""

import contextlib

from pypinyin import Style, lazy_pinyin

from app.core.constants import TRANSLATION_SOURCE_CEDICT, TRANSLATION_SOURCE_MYMEMORY
from app.core.radicals import CHAR_TO_RADICAL, RADICAL_PINYIN
from app.services.translation import get_translation_with_source
from app.state import cedict_vocab, hsk_vocab, unknown_word_cache


async def lookup_unknown_word(word: str) -> dict | None:
    """Look up an unknown word online and cache the result."""
    if word in unknown_word_cache:
        return unknown_word_cache[word]

    word_pinyin = " ".join(lazy_pinyin(word, style=Style.TONE))
    translation_result = await get_translation_with_source(word)
    if not translation_result:
        return None

    word_info = {
        "pinyin": word_pinyin,
        "meaning": translation_result["translation"],
        "meanings": [translation_result["translation"]],
        "level": "unknown",
        "frequency": 0,
        "translation_source": translation_result.get("source", TRANSLATION_SOURCE_MYMEMORY),
    }
    unknown_word_cache[word] = word_info
    return word_info


def _char_component_stats(chars: list[str]) -> dict:
    """
    Per-character pinyin/meaning/radical/level roll-up, shared by
    `create_compound_from_hsk` (glue-together fallback) and
    `resolve_from_cedict` (HSK-level colouring for a CEDICT-resolved word).
    Every char must already be confirmed present in `hsk_vocab` by the caller.
    """
    char_pinyins: list = []
    char_levels_new: list = []
    char_levels_old: list = []
    char_meanings: list = []
    char_radicals: list = []
    char_radical_pinyins: list = []

    for char in chars:
        char_data = hsk_vocab[char]
        char_pinyins.append(char_data["pinyin"])
        char_meanings.append(char_data["meaning"])

        char_radical = char_data.get("radical", "") or CHAR_TO_RADICAL.get(char, "")
        if char_radical:
            char_radicals.append(char_radical)
            if char_radical in hsk_vocab:
                char_radical_pinyins.append(hsk_vocab[char_radical].get("pinyin", ""))
            elif char_radical in RADICAL_PINYIN:
                char_radical_pinyins.append(RADICAL_PINYIN[char_radical])
            else:
                char_radical_pinyins.append("")

        level_new = char_data.get("level_new")
        if level_new:
            level_new_str = level_new.replace("new-", "").replace("+", "")
            try:
                char_levels_new.append(int(level_new_str))
            except ValueError:
                char_levels_new.append(1)

        level_old = char_data.get("level_old")
        if level_old:
            level_old_str = level_old.replace("old-", "")
            with contextlib.suppress(ValueError):
                char_levels_old.append(int(level_old_str))

    level_new = f"new-{max(char_levels_new)}" if char_levels_new else None
    level_old = f"old-{max(char_levels_old)}" if char_levels_old else None
    return {
        "pinyin": " ".join(char_pinyins),
        "meaning": " + ".join(char_meanings),
        "meanings": char_meanings,
        "level_new": level_new,
        "level_old": level_old,
        "level": level_new or level_old or "new-1",
        "radical": " + ".join(char_radicals) if char_radicals else "",
        "radical_pinyin": " + ".join(char_radical_pinyins) if char_radical_pinyins else "",
    }


def resolve_from_cedict(word: str) -> dict | None:
    """
    Direct CC-CEDICT hit for a multi-character word jieba segmented as one
    token but that isn't in `hsk_vocab` itself (e.g. "一个", "变得") — very
    common, correctly-segmented words that would otherwise fall through to
    `create_compound_from_hsk`'s per-character glue ("one + used in 自個兒")
    or a flaky online-translation call. Checked before both, since a curated
    CEDICT gloss beats either.

    Returns None if `word` isn't in `cedict_vocab`. When every character of
    `word` is itself in `hsk_vocab`, HSK level/radical are derived from the
    components (same as a compound) so the word still gets HSK colouring in
    the reader; otherwise those fields are left unset, same as an "unknown"
    online-resolved word.
    """
    entry = cedict_vocab.get(word)
    if entry is None:
        return None

    chars = list(word)
    stats = _char_component_stats(chars) if all(c in hsk_vocab for c in chars) else {}

    return {
        "pinyin": entry.get("pinyin") or stats.get("pinyin", ""),
        "meaning": entry["meaning"],
        "meanings": entry.get("meanings") or [entry["meaning"]],
        "level": stats.get("level", "unknown"),
        "level_new": stats.get("level_new"),
        "level_old": stats.get("level_old"),
        "frequency": 0,
        "translation_source": TRANSLATION_SOURCE_CEDICT,
        "radical": stats.get("radical", ""),
        "radical_pinyin": stats.get("radical_pinyin", ""),
    }


async def create_compound_from_hsk(word: str) -> dict | None:
    """
    Build compound word info from in-HSK characters. Returns None unless every
    character of the word is present in `hsk_vocab`.
    """
    chars = list(word)
    if not all(char in hsk_vocab for char in chars):
        return None

    stats = _char_component_stats(chars)
    compound_pinyin = stats["pinyin"]
    compound_level_new = stats["level_new"]
    compound_level_old = stats["level_old"]
    fallback_meaning = stats["meaning"]
    compound_radical = stats["radical"]
    compound_radical_pinyin = stats["radical_pinyin"]

    translation_result = await get_translation_with_source(word)
    if translation_result:
        translation = translation_result["translation"]
        source = translation_result["source"]
        # If the "translation" is just romanised pinyin or too short to be useful,
        # fall back to gluing character glosses together.
        if len(translation) < 3 or translation.lower() == compound_pinyin.lower().replace(" ", ""):
            translation = fallback_meaning
            source = "hsk-chars"

        return {
            "pinyin": compound_pinyin,
            "meaning": translation,
            "meanings": [translation],
            "level": stats["level"],
            "level_new": compound_level_new,
            "level_old": compound_level_old,
            "frequency": 0,
            "translation_source": source,
            "radical": compound_radical,
            "radical_pinyin": compound_radical_pinyin,
        }

    return {
        "pinyin": compound_pinyin,
        "meaning": fallback_meaning,
        "meanings": stats["meanings"],
        "level": stats["level"],
        "level_new": compound_level_new,
        "level_old": compound_level_old,
        "frequency": 0,
        "translation_source": "hsk-chars",
        "radical": compound_radical,
        "radical_pinyin": compound_radical_pinyin,
    }
