"""
Data migrations from the legacy single-HSK-level shape to the dual
new-HSK / old-HSK shape. Run on saved texts and vocabulary lists at
read time so old user content keeps working.
"""

from app.services.levels import hsk_statistics
from app.services.word_lookup import char_components
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
            stats = char_components(chars)
            word_data["level_new"] = stats["level_new"]
            word_data["level_old"] = stats["level_old"]
            if stats["level_new"] or stats["level_old"]:
                word_data["hsk_level"] = stats["level"]
            word_data["radical"] = stats["radical"]
            word_data["radical_pinyin"] = stats["radical_pinyin"]
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
