"""
Word-info lookup for tokens missing from the HSK vocabulary.

Two strategies, tried in this order by `app.services.segmentation`:
- `resolve_from_cedict`: a direct CC-CEDICT hit for the whole segment.
- `describe_non_word`: everything else. Segmentation already splits
  non-dictionary phrases into dictionary words, so this only sees the
  leftovers (and every token while CC-CEDICT is not loaded). It gives a
  reading and the token's dictionary parts, never a meaning: neither
  per-character glue ("very + many") nor a machine translation of the
  isolated token (十点 -> "half-witted") is a gloss worth showing or
  storing. Sentence translation is separate (`translation.py`).
"""

import contextlib

from pypinyin import Style, lazy_pinyin

from app.core.constants import TRANSLATION_SOURCE_CEDICT, TRANSLATION_SOURCE_PARTS
from app.core.radicals import CHAR_TO_RADICAL, RADICAL_PINYIN
from app.services.lexicon import is_cjk_char
from app.services.readings import readings_payload
from app.services.word_info import cedict_entry, word_parts
from app.state import hsk_vocab


def _char_component_stats(chars: list[str]) -> dict:
    """
    Per-character pinyin/radical/level roll-up, used for the HSK-level
    colouring of words that are not HSK headwords themselves. There is
    deliberately no meaning here: joined character glosses are not a gloss.
    Every char must already be confirmed present in `hsk_vocab` by the caller.
    """
    char_pinyins: list = []
    char_levels_new: list = []
    char_levels_old: list = []
    char_radicals: list = []
    char_radical_pinyins: list = []

    for char in chars:
        char_data = hsk_vocab[char]
        char_pinyins.append(char_data["pinyin"])

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
        "level_new": level_new,
        "level_old": level_old,
        "level": level_new or level_old or "new-1",
        "radical": " + ".join(char_radicals) if char_radicals else "",
        "radical_pinyin": " + ".join(char_radical_pinyins) if char_radical_pinyins else "",
    }


def resolve_from_cedict(word: str) -> dict | None:
    """
    Direct CC-CEDICT hit for a token that isn't in `hsk_vocab` itself:
    a multi-character word jieba segmented as one token (e.g. "一个",
    "变得") — very common, correctly-segmented words that would otherwise
    fall through to the per-character breakdown of `describe_non_word` —
    or a character outside HSK (喵). A variant or traditional form (玅)
    reads its headword's entry (妙) and carries "variant of 妙" as a tag.

    Returns None if CC-CEDICT doesn't know `word`. When every character of
    `word` is itself in `hsk_vocab`, HSK level/radical are derived from the
    components (same as a compound) so the word still gets HSK colouring in
    the reader; otherwise those fields are left unset.
    """
    entry, headword = cedict_entry(word)
    if entry is None:
        return None
    tags = list(entry.get("meaning_tags") or [])
    if headword:
        tags.append(f"variant of {headword}")

    chars = list(word)
    stats = _char_component_stats(chars) if all(c in hsk_vocab for c in chars) else {}

    return {
        "pinyin": entry.get("pinyin") or stats.get("pinyin", ""),
        "meaning": entry["meaning"],
        "meanings": entry.get("meanings") or [entry["meaning"]],
        "meaning_tags": tags,
        "readings": readings_payload(entry),
        "level": stats.get("level", "unknown"),
        "level_new": stats.get("level_new"),
        "level_old": stats.get("level_old"),
        "frequency": 0,
        "translation_source": TRANSLATION_SOURCE_CEDICT,
        "radical": stats.get("radical", ""),
        "radical_pinyin": stats.get("radical_pinyin", ""),
    }


def describe_non_word(word: str, extra=()) -> dict | None:
    """Reader info for a multi-character CJK token no dictionary lists:
    pypinyin reading, empty meaning and the dictionary `parts` it is made
    of. HSK colouring comes from the characters when all of them are in
    HSK. Returns None for tokens without Chinese characters."""
    if not any(is_cjk_char(c) for c in word):
        return None
    chars = list(word)
    stats = _char_component_stats(chars) if all(c in hsk_vocab for c in chars) else {}
    return {
        "pinyin": " ".join(lazy_pinyin(word, style=Style.TONE)),
        "meaning": "",
        "meanings": [],
        "parts": word_parts(word, extra),
        "level": stats.get("level", "unknown"),
        "level_new": stats.get("level_new"),
        "level_old": stats.get("level_old"),
        "frequency": 0,
        "translation_source": TRANSLATION_SOURCE_PARTS,
        "radical": stats.get("radical", ""),
        "radical_pinyin": stats.get("radical_pinyin", ""),
    }
