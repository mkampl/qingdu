"""
Word-info lookup for terms missing from the HSK vocabulary.

Two strategies:
- `lookup_unknown_word`: pure online translation + pypinyin fallback.
- `create_compound_from_hsk`: build a compound entry from the HSK character
  components when every character of the word is known, then enrich with an
  online translation (falling back to the per-character glosses if the
  online result looks like pinyin or is too short to be useful).
"""

from typing import Dict, Optional

from pypinyin import Style, lazy_pinyin

from app.core.constants import TRANSLATION_SOURCE_MYMEMORY
from app.core.radicals import CHAR_TO_RADICAL, RADICAL_PINYIN
from app.services.translation import get_translation_with_source
from app.state import hsk_vocab, unknown_word_cache


async def lookup_unknown_word(word: str) -> Optional[Dict]:
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


async def create_compound_from_hsk(word: str) -> Optional[Dict]:
    """
    Build compound word info from in-HSK characters. Returns None unless every
    character of the word is present in `hsk_vocab`.
    """
    chars = list(word)
    char_pinyins: list = []
    char_levels_new: list = []
    char_levels_old: list = []
    char_meanings: list = []
    char_radicals: list = []
    char_radical_pinyins: list = []

    for char in chars:
        if char not in hsk_vocab:
            return None

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
            try:
                char_levels_old.append(int(level_old_str))
            except ValueError:
                pass

    compound_pinyin = " ".join(char_pinyins)
    compound_level_new = f"new-{max(char_levels_new)}" if char_levels_new else None
    compound_level_old = f"old-{max(char_levels_old)}" if char_levels_old else None
    compound_level = compound_level_new or compound_level_old or "new-1"
    fallback_meaning = " + ".join(char_meanings)
    compound_radical = " + ".join(char_radicals) if char_radicals else ""
    compound_radical_pinyin = (
        " + ".join(char_radical_pinyins) if char_radical_pinyins else ""
    )

    translation_result = await get_translation_with_source(word)
    if translation_result:
        translation = translation_result["translation"]
        source = translation_result["source"]
        # If the "translation" is just romanised pinyin or too short to be useful,
        # fall back to gluing character glosses together.
        if (
            len(translation) < 3
            or translation.lower() == compound_pinyin.lower().replace(" ", "")
        ):
            translation = fallback_meaning
            source = "hsk-chars"

        return {
            "pinyin": compound_pinyin,
            "meaning": translation,
            "meanings": [translation],
            "level": compound_level,
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
        "meanings": char_meanings,
        "level": compound_level,
        "level_new": compound_level_new,
        "level_old": compound_level_old,
        "frequency": 0,
        "translation_source": "hsk-chars",
        "radical": compound_radical,
        "radical_pinyin": compound_radical_pinyin,
    }
