"""
Chinese text segmentation + HSK enrichment.

The route handler in `app.routers.analyze` is a thin wrapper around
`analyze_chinese_text` — keep all the segmentation logic here.
"""

import logging

import jieba

from app.core.constants import TRANSLATION_SOURCE_HSK
from app.schemas import WordInfo
from app.services.levels import estimate_text_level
from app.services.word_lookup import create_compound_from_hsk, lookup_unknown_word
from app.state import hsk_vocab

logger = logging.getLogger(__name__)


def get_word_info(word: str) -> dict | None:
    """Look up a word in the HSK vocab. Returns None if not found."""
    return hsk_vocab.get(word)


def _increment_level(stats: dict, total: int, level: str | None, prefix: str) -> int:
    """
    Increment the stats bucket for `level` (e.g. "new-3" -> "hsk3").
    Returns the new total (caller does `total = _increment_level(...)`).
    """
    if not level:
        return total
    level_num = level.replace(prefix, "").replace("+", "")
    try:
        key = f"hsk{int(level_num)}"
        if key in stats:
            stats[key] += 1
        return total + 1
    except ValueError:
        return total


async def analyze_chinese_text(text: str) -> dict:
    """
    Segment `text` with jieba, look each word up in the HSK vocab (falling back
    to compound-from-characters or an online lookup), and return per-word data
    plus aggregate statistics across both HSK systems.
    """
    text = text.strip()
    if not text:
        return {"words": [], "statistics": {}}

    # Split by line breaks first so we can preserve them in the output.
    lines = text.split("\n")
    segments: list = []
    for i, line in enumerate(lines):
        if line.strip():
            segments.extend(list(jieba.cut(line)))
        if i < len(lines) - 1:
            segments.append("\n")

    words: list = []
    hsk_stats_new = {f"hsk{i}": 0 for i in range(1, 10)}
    hsk_stats_old = {f"hsk{i}": 0 for i in range(1, 7)}  # Old HSK has 6 levels
    total_hsk_words_new = 0
    total_hsk_words_old = 0

    for segment in segments:
        if segment == "\n":
            words.append(
                WordInfo(
                    text="\n",
                    is_hsk=False,
                    hsk_level="",
                    pinyin="",
                    meaning="",
                    meanings=[],
                    frequency=0,
                    translation_source="linebreak",
                ).dict()
            )
            continue

        word_info = WordInfo(text=segment)
        vocab_entry = get_word_info(segment)

        if vocab_entry:
            word_info.hsk_level = vocab_entry["level"]
            word_info.level_new = vocab_entry.get("level_new")
            word_info.level_old = vocab_entry.get("level_old")
            word_info.pinyin = vocab_entry["pinyin"]
            word_info.meaning = vocab_entry["meaning"]
            word_info.meanings = vocab_entry["meanings"]
            word_info.frequency = vocab_entry["frequency"]
            word_info.is_hsk = True
            word_info.translation_source = TRANSLATION_SOURCE_HSK
            word_info.radical = vocab_entry.get("radical", "")
            word_info.radical_pinyin = vocab_entry.get("radical_pinyin", "")
            total_hsk_words_new = _increment_level(
                hsk_stats_new, total_hsk_words_new, vocab_entry.get("level_new"), "new-"
            )
            total_hsk_words_old = _increment_level(
                hsk_stats_old, total_hsk_words_old, vocab_entry.get("level_old"), "old-"
            )
        elif len(segment) > 1:
            # Unknown multi-character word — try compound first, then online.
            chars = list(segment)
            if all(char in hsk_vocab for char in chars):
                compound_info = await create_compound_from_hsk(segment)
                if compound_info:
                    word_info.hsk_level = compound_info["level"]
                    word_info.level_new = compound_info.get("level_new")
                    word_info.level_old = compound_info.get("level_old")
                    word_info.pinyin = compound_info["pinyin"]
                    word_info.meaning = compound_info["meaning"]
                    word_info.meanings = compound_info["meanings"]
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    word_info.translation_source = compound_info.get("translation_source")
                    word_info.radical = compound_info.get("radical", "")
                    word_info.radical_pinyin = compound_info.get("radical_pinyin", "")
                    total_hsk_words_new = _increment_level(
                        hsk_stats_new,
                        total_hsk_words_new,
                        compound_info.get("level_new"),
                        "new-",
                    )
                    total_hsk_words_old = _increment_level(
                        hsk_stats_old,
                        total_hsk_words_old,
                        compound_info.get("level_old"),
                        "old-",
                    )
            else:
                online_info = await lookup_unknown_word(segment)
                if online_info:
                    word_info.hsk_level = "unknown"
                    word_info.level_new = None
                    word_info.level_old = None
                    word_info.pinyin = online_info["pinyin"]
                    word_info.meaning = online_info["meaning"]
                    word_info.meanings = online_info["meanings"]
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    word_info.translation_source = online_info.get("translation_source")

        words.append(word_info.dict())

    estimated_level_new = estimate_text_level(hsk_stats_new, total_hsk_words_new)
    estimated_level_old = estimate_text_level(hsk_stats_old, total_hsk_words_old)

    return {
        "words": words,
        "statistics": {
            "total_characters": len(text),
            "total_words": len(segments),
            "hsk_words_new": total_hsk_words_new,
            "hsk_distribution_new": hsk_stats_new,
            "estimated_level_new": estimated_level_new,
            "hsk_words_old": total_hsk_words_old,
            "hsk_distribution_old": hsk_stats_old,
            "estimated_level_old": estimated_level_old,
            # Legacy fields (for backwards compatibility — use new HSK).
            "hsk_words": total_hsk_words_new,
            "hsk_distribution": hsk_stats_new,
            "estimated_level": estimated_level_new,
        },
    }
