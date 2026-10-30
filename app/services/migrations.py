"""
Data migrations from the legacy single-HSK-level shape to the dual
new-HSK / old-HSK shape. Run on saved texts and vocabulary lists at
read time so old user content keeps working.
"""

from app.core.radicals import CHAR_TO_RADICAL, RADICAL_PINYIN
from app.services.levels import hsk_statistics, level_number
from app.state import hsk_vocab


def migrate_word_data(word_data: dict) -> dict:
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
                if (n := level_number(char_data.get("level_new"))) is not None:
                    char_levels_new.append(n)
                if (n := level_number(char_data.get("level_old"), ("old-",))) is not None:
                    char_levels_old.append(n)

            word_data["level_new"] = f"new-{max(char_levels_new)}" if char_levels_new else None
            word_data["level_old"] = f"old-{max(char_levels_old)}" if char_levels_old else None

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


def _assign_legacy_level(word_data: dict, old_level: str) -> None:
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


def migrate_analysis_data(analysis_data: dict) -> dict:
    """
    Migrate a saved analysis blob to the dual-HSK shape and recompute the
    statistics summary for both new and old HSK systems.
    """
    if not analysis_data or "words" not in analysis_data:
        return analysis_data

    migrated_words = [migrate_word_data(w) for w in analysis_data["words"]]
    analysis_data["words"] = migrated_words

    stats = analysis_data.setdefault("statistics", {})
    stats.update(
        hsk_statistics(
            (w.get("level_new"), w.get("level_old")) for w in migrated_words if w.get("is_hsk")
        )
    )

    return analysis_data


def migrate_vocabulary_sections(sections: list[dict]) -> list[dict]:
    """Migrate every word in every section of a vocabulary list."""
    if not sections:
        return sections

    for section in sections:
        if section.get("words"):
            section["words"] = [migrate_word_data(w) for w in section["words"]]
    return sections
