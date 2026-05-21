"""
Data migrations from the legacy single-HSK-level shape to the dual
new-HSK / old-HSK shape. Run on saved texts and vocabulary lists at
read time so old user content keeps working.
"""

from typing import Dict, List

from app.core.radicals import CHAR_TO_RADICAL, RADICAL_PINYIN
from app.services.levels import estimate_text_level
from app.state import hsk_vocab


def migrate_word_data(word_data: Dict) -> Dict:
    """
    Migrate a single word dict to the dual-HSK shape (`level_new`, `level_old`).
    Idempotent — returns the input untouched if it already has either field.
    """
    if "level_new" in word_data or "level_old" in word_data:
        return word_data

    old_level = word_data.get("hsk_level") or word_data.get("level")
    if not old_level:
        return word_data

    word_text = word_data.get("text") or word_data.get("word")

    if word_text and word_text in hsk_vocab:
        vocab_entry = hsk_vocab[word_text]
        word_data["level_new"] = vocab_entry.get("level_new")
        word_data["level_old"] = vocab_entry.get("level_old")
        word_data["hsk_level"] = vocab_entry.get("level")
        word_data["radical"] = vocab_entry.get("radical", "")
        word_data["radical_pinyin"] = vocab_entry.get("radical_pinyin", "")
    elif word_text and len(word_text) > 1:
        chars = list(word_text)
        if all(char in hsk_vocab for char in chars):
            char_levels_new: list = []
            char_levels_old: list = []
            for char in chars:
                char_data = hsk_vocab[char]
                level_new = char_data.get("level_new")
                if level_new:
                    try:
                        char_levels_new.append(
                            int(level_new.replace("new-", "").replace("+", ""))
                        )
                    except (ValueError, AttributeError):
                        pass
                level_old = char_data.get("level_old")
                if level_old:
                    try:
                        char_levels_old.append(int(level_old.replace("old-", "")))
                    except (ValueError, AttributeError):
                        pass

            word_data["level_new"] = (
                f"new-{max(char_levels_new)}" if char_levels_new else None
            )
            word_data["level_old"] = (
                f"old-{max(char_levels_old)}" if char_levels_old else None
            )

            if word_data["level_new"]:
                word_data["hsk_level"] = word_data["level_new"]
            elif word_data["level_old"]:
                word_data["hsk_level"] = word_data["level_old"]

            char_radicals: list = []
            char_radical_pinyins: list = []
            for char in chars:
                char_data = hsk_vocab[char]
                char_radical = char_data.get("radical", "") or CHAR_TO_RADICAL.get(char, "")
                if char_radical:
                    char_radicals.append(char_radical)
                    if char_radical in hsk_vocab:
                        char_radical_pinyins.append(hsk_vocab[char_radical].get("pinyin", ""))
                    elif char_radical in RADICAL_PINYIN:
                        char_radical_pinyins.append(RADICAL_PINYIN[char_radical])
                    else:
                        char_radical_pinyins.append("")

            word_data["radical"] = " + ".join(char_radicals) if char_radicals else ""
            word_data["radical_pinyin"] = (
                " + ".join(char_radical_pinyins) if char_radical_pinyins else ""
            )
            return word_data
        else:
            _assign_legacy_level(word_data, old_level)
    else:
        _assign_legacy_level(word_data, old_level)

    word_data.setdefault("radical", "")
    word_data.setdefault("radical_pinyin", "")
    return word_data


def _assign_legacy_level(word_data: Dict, old_level: str) -> None:
    """Best-effort assignment when we can't look up component characters."""
    if old_level.startswith("new-"):
        word_data["level_new"] = old_level
        word_data["level_old"] = None
    elif old_level.startswith("old-"):
        word_data["level_new"] = None
        word_data["level_old"] = old_level
    else:
        word_data["level_new"] = old_level
        word_data["level_old"] = None


def migrate_analysis_data(analysis_data: Dict) -> Dict:
    """
    Migrate a saved analysis blob to the dual-HSK shape and recompute the
    statistics summary for both new and old HSK systems.
    """
    if not analysis_data or "words" not in analysis_data:
        return analysis_data

    migrated_words = [migrate_word_data(w) for w in analysis_data["words"]]
    analysis_data["words"] = migrated_words

    hsk_stats_new = {f"hsk{i}": 0 for i in range(1, 10)}
    hsk_stats_old = {f"hsk{i}": 0 for i in range(1, 7)}
    total_hsk_words_new = 0
    total_hsk_words_old = 0

    for word in migrated_words:
        if not word.get("is_hsk"):
            continue

        level_new = word.get("level_new")
        if level_new:
            level_new_num = level_new.replace("new-", "").replace("+", "")
            try:
                key = f"hsk{int(level_new_num)}"
                if key in hsk_stats_new:
                    hsk_stats_new[key] += 1
                total_hsk_words_new += 1
            except ValueError:
                pass

        level_old = word.get("level_old")
        if level_old:
            level_old_num = level_old.replace("old-", "")
            try:
                key = f"hsk{int(level_old_num)}"
                if key in hsk_stats_old:
                    hsk_stats_old[key] += 1
                total_hsk_words_old += 1
            except ValueError:
                pass

    estimated_level_new = estimate_text_level(hsk_stats_new, total_hsk_words_new)
    estimated_level_old = estimate_text_level(hsk_stats_old, total_hsk_words_old)

    stats = analysis_data.setdefault("statistics", {})
    stats["hsk_words_new"] = total_hsk_words_new
    stats["hsk_distribution_new"] = hsk_stats_new
    stats["estimated_level_new"] = estimated_level_new
    stats["hsk_words_old"] = total_hsk_words_old
    stats["hsk_distribution_old"] = hsk_stats_old
    stats["estimated_level_old"] = estimated_level_old
    # Legacy fields kept around for backwards compatibility — point at new HSK.
    stats["hsk_words"] = total_hsk_words_new
    stats["hsk_distribution"] = hsk_stats_new
    stats["estimated_level"] = estimated_level_new

    return analysis_data


def migrate_vocabulary_sections(sections: List[Dict]) -> List[Dict]:
    """Migrate every word in every section of a vocabulary list."""
    if not sections:
        return sections

    for section in sections:
        if section.get("words"):
            section["words"] = [migrate_word_data(w) for w in section["words"]]
    return sections
