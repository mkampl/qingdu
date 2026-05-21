"""
HSK vocabulary loader.

Downloads the complete-hsk-vocabulary JSON from GitHub, processes it into
the dual New-HSK / Old-HSK shape, supplements missing levels from character
components, applies the authoritative Konfuzius-Institut old-HSK overrides,
and writes the result to disk for offline restart.

Mutates `app.state.hsk_vocab` and `app.state.hsk_lists_original` in place.
"""

import json
import logging
from datetime import datetime

import httpx
from pypinyin import Style, lazy_pinyin
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.constants import (
    HSK_DOWNLOAD_TIMEOUT,
    HSK_RETRY_MAX_WAIT,
    HSK_RETRY_MIN_WAIT,
    HSK_VOCAB_URL,
    MAX_RETRY_ATTEMPTS,
)
from app.core.paths import BACKUP_DIR, DATA_DIR
from app.core.radicals import CHAR_TO_RADICAL, RADICAL_PINYIN
from app.konfuzius_parser import parse_konfuzius_old_hsk
from app.state import hsk_lists_original, hsk_vocab

logger = logging.getLogger(__name__)


def cleanup_old_backups(max_age_days: int = 30) -> None:
    """Remove backup files older than `max_age_days`. Best-effort — never raises."""
    try:
        now = datetime.now()
        deleted_count = 0
        for backup_file in BACKUP_DIR.glob("*.json"):
            try:
                date_str = backup_file.stem.split("_")[-1]
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                age_days = (now - file_date).days
                if age_days > max_age_days:
                    backup_file.unlink()
                    deleted_count += 1
                    logger.info(
                        f"Deleted old backup: {backup_file.name} (age: {age_days} days)"
                    )
            except (ValueError, IndexError):
                # Filename doesn't match expected pattern; skip.
                continue
        if deleted_count > 0:
            logger.info(f"Cleanup complete: removed {deleted_count} old backup(s)")
    except Exception as e:
        logger.warning(f"Backup cleanup failed: {e}")


def _choose_best_form(forms: list) -> dict | None:
    """Prefer the first form that isn't a surname/abbreviation; else fall back."""
    best_form = None
    fallback_form = None
    for form in forms:
        meanings = form.get("meanings", [])
        if not meanings:
            continue
        first_meaning = meanings[0]
        if fallback_form is None:
            fallback_form = form
        if first_meaning.startswith("surname ") or first_meaning.startswith("abbr. for "):
            continue
        best_form = form
        break
    return best_form or fallback_form


def _extract_levels(levels: list) -> tuple[str | None, str | None]:
    """Pull out (level_new, level_old) tags from the raw GitHub `level` array."""
    level_new = None
    level_old = None
    for level in levels:
        if isinstance(level, str):
            if level.startswith("new-"):
                level_new = level
            elif level.startswith("old-"):
                level_old = level
    return level_new, level_old


def _backup_raw(raw_data: list) -> None:
    """Write a dated raw-source backup and prune old backups."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        raw_backup_file = BACKUP_DIR / f"complete_hsk_{today}.json"
        if not raw_backup_file.exists():
            with open(raw_backup_file, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Backup saved: {raw_backup_file.name}")
            cleanup_old_backups(max_age_days=30)
    except Exception as e:
        logger.warning(f"Failed to create backup (non-critical): {e}")


def _add_character_components(
    char_levels_new: dict, char_levels_old: dict
) -> None:
    """For each single character seen in source, ensure an entry exists in vocab."""
    all_chars = set(char_levels_new) | set(char_levels_old)
    for char in all_chars:
        if char in hsk_vocab:
            continue
        char_pinyin = " ".join(lazy_pinyin(char, style=Style.TONE))
        level_new_num = char_levels_new.get(char)
        level_old_num = char_levels_old.get(char)
        char_level_new = f"new-{level_new_num}" if level_new_num else None
        char_level_old = f"old-{level_old_num}" if level_old_num else None
        primary_level = char_level_new or char_level_old
        display_num = level_new_num or level_old_num
        hsk_vocab[char] = {
            "pinyin": char_pinyin,
            "meaning": f"(character, HSK {display_num})",
            "meanings": ["character component"],
            "level": primary_level,
            "level_new": char_level_new,
            "level_old": char_level_old,
            "frequency": 0,
            "is_original_hsk": False,
        }


def _supplement_missing_levels() -> None:
    """For multi-character words missing level_new/level_old, infer from chars."""
    supplemented_new = 0
    supplemented_old = 0
    for word, word_data in hsk_vocab.items():
        if len(word) == 1 or word_data.get("meaning", "").startswith("(character"):
            continue
        word_data.setdefault("is_original_hsk", False)

        has_level_new = bool(word_data.get("level_new"))
        has_level_old = bool(word_data.get("level_old"))
        if has_level_new and has_level_old:
            continue

        chars = list(word)

        if not word_data.get("level_new"):
            char_levels_list: list = []
            ok = True
            for char in chars:
                if char in hsk_vocab and hsk_vocab[char].get("level_new"):
                    level_str = hsk_vocab[char]["level_new"].replace("new-", "").replace("+", "")
                    try:
                        char_levels_list.append(int(level_str))
                    except ValueError:
                        ok = False
                        break
                else:
                    ok = False
                    break
            if ok and char_levels_list:
                word_data["level_new"] = f"new-{max(char_levels_list)}"
                if not word_data.get("level"):
                    word_data["level"] = word_data["level_new"]
                supplemented_new += 1

        if not word_data.get("level_old"):
            # More pragmatic for old HSK: don't require ALL chars to have level_old.
            char_levels_list = []
            for char in chars:
                if char in hsk_vocab and hsk_vocab[char].get("level_old"):
                    level_str = hsk_vocab[char]["level_old"].replace("old-", "")
                    try:
                        char_levels_list.append(int(level_str))
                    except ValueError:
                        pass
            if char_levels_list:
                word_data["level_old"] = f"old-{max(char_levels_list)}"
                supplemented_old += 1

    if supplemented_new or supplemented_old:
        logger.info(
            f"Supplemented missing levels from characters: "
            f"{supplemented_new} level_new, {supplemented_old} level_old"
        )


def _populate_radical_pinyin() -> None:
    """Set radical_pinyin on every entry from the HSK vocab or radical-pinyin map."""
    radical_pinyin_added = 0
    radical_from_mapping = 0
    for _word, word_data in hsk_vocab.items():
        radical = word_data.get("radical", "")
        if not radical:
            word_data["radical_pinyin"] = ""
            continue
        if radical in hsk_vocab:
            word_data["radical_pinyin"] = hsk_vocab[radical].get("pinyin", "")
            radical_pinyin_added += 1
        elif radical in RADICAL_PINYIN:
            word_data["radical_pinyin"] = RADICAL_PINYIN[radical]
            radical_from_mapping += 1
        else:
            word_data["radical_pinyin"] = ""
    if radical_pinyin_added or radical_from_mapping:
        logger.info(
            f"Added radical pinyin: {radical_pinyin_added} from vocabulary, "
            f"{radical_from_mapping} from mapping"
        )


def _combine_multi_char_radicals() -> None:
    """For words longer than one character, glue together per-character radicals."""
    multi_char_radicals_updated = 0
    chars_missing_radicals = 0
    for word, word_data in hsk_vocab.items():
        if len(word) <= 1:
            continue
        char_radicals: list = []
        char_radical_pinyins: list = []
        for char in word:
            char_radical = ""
            char_radical_pinyin = ""
            if char in hsk_vocab:
                char_data = hsk_vocab[char]
                char_radical = char_data.get("radical", "")
                char_radical_pinyin = char_data.get("radical_pinyin", "")
            if not char_radical and char in CHAR_TO_RADICAL:
                char_radical = CHAR_TO_RADICAL[char]
                if char_radical in RADICAL_PINYIN:
                    char_radical_pinyin = RADICAL_PINYIN[char_radical]
            if char_radical:
                char_radicals.append(char_radical)
                char_radical_pinyins.append(char_radical_pinyin)
            else:
                chars_missing_radicals += 1
                logger.debug(
                    f"Character '{char}' in word '{word}' is missing radical data"
                )
        if char_radicals:
            word_data["radical"] = " + ".join(char_radicals)
            word_data["radical_pinyin"] = " + ".join(char_radical_pinyins)
            multi_char_radicals_updated += 1
    if multi_char_radicals_updated:
        logger.info(
            f"Updated radicals for {multi_char_radicals_updated} multi-character words"
        )
    if chars_missing_radicals:
        logger.warning(
            f"Found {chars_missing_radicals} characters missing radical data in "
            "multi-character words"
        )


def _apply_konfuzius_old_hsk() -> None:
    """Override old-HSK levels with the Konfuzius-Institut authoritative list."""
    konfuzius_file = DATA_DIR / "konfuzius" / "old_hsk_levels.txt"
    if not konfuzius_file.exists():
        logger.warning(f"Konfuzius Old HSK file not found: {konfuzius_file}")
        return
    try:
        konfuzius_vocab = parse_konfuzius_old_hsk(konfuzius_file)
        applied = 0
        updated = 0
        for hanzi, konfuzius_level in konfuzius_vocab.items():
            if hanzi in hsk_vocab:
                old_level = hsk_vocab[hanzi].get("level_old")
                if old_level != konfuzius_level:
                    updated += 1
                hsk_vocab[hanzi]["level_old"] = konfuzius_level
                applied += 1
            if hanzi in hsk_lists_original:
                hsk_lists_original[hanzi]["level_old"] = konfuzius_level
        logger.info(
            f"Applied Konfuzius Institut Old HSK levels: {applied} words total, "
            f"{updated} updated from GitHub source"
        )
        konfuzius_dist: dict = {}
        for level in konfuzius_vocab.values():
            level_num = level.replace("old-", "")
            konfuzius_dist[level_num] = konfuzius_dist.get(level_num, 0) + 1
        logger.info("Konfuzius Institut Old HSK distribution:")
        for level in sorted(konfuzius_dist, key=int):
            logger.info(f"  Level {level}: {konfuzius_dist[level]} words")
    except Exception as e:
        logger.error(f"Failed to load Konfuzius Old HSK levels (non-critical): {e}")


def _save_processed() -> None:
    """Persist the processed vocabulary + a dated backup."""
    vocab_file = DATA_DIR / "hsk_vocabulary.json"
    with open(vocab_file, "w", encoding="utf-8") as f:
        json.dump(hsk_vocab, f, ensure_ascii=False, indent=2)

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        processed_backup_file = BACKUP_DIR / f"hsk_vocabulary_{today}.json"
        if not processed_backup_file.exists():
            with open(processed_backup_file, "w", encoding="utf-8") as f:
                json.dump(hsk_vocab, f, ensure_ascii=False, indent=2)
            logger.info(f"Processed vocabulary backup saved: {processed_backup_file.name}")
    except Exception as e:
        logger.warning(f"Failed to backup processed vocabulary (non-critical): {e}")


@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=HSK_RETRY_MIN_WAIT, max=HSK_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    reraise=True,
)
async def download_hsk_vocabulary() -> None:
    """
    Download and process the complete HSK vocabulary.
    Retries with exponential backoff on network errors.
    """
    try:
        async with httpx.AsyncClient(timeout=HSK_DOWNLOAD_TIMEOUT) as client:
            response = await client.get(HSK_VOCAB_URL)
            response.raise_for_status()
            raw_data = response.json()

        _backup_raw(raw_data)

        processed = 0
        char_levels_new: dict = {}
        char_levels_old: dict = {}
        total_entries = 0
        entries_with_both = 0
        entries_with_new_only = 0
        entries_with_old_only = 0
        old_level_words: dict = {f"{i}": [] for i in range(1, 7)}

        for entry in raw_data:
            total_entries += 1
            if not isinstance(entry, dict):
                continue
            simplified = entry.get("simplified")
            if not simplified:
                continue
            levels = entry.get("level", [])
            if not levels:
                continue
            forms = entry.get("forms", [])
            if not forms:
                continue

            best_form = _choose_best_form(forms) or forms[0]
            transcriptions = best_form.get("transcriptions", {})
            pinyin = transcriptions.get("pinyin", "")
            meanings = best_form.get("meanings", [])

            level_new, level_old = _extract_levels(levels)
            if level_new and level_old:
                entries_with_both += 1
            elif level_new:
                entries_with_new_only += 1
            elif level_old:
                entries_with_old_only += 1

            if (level_new or level_old) and simplified:
                radical = entry.get("radical", "")
                new_entry = {
                    "pinyin": pinyin,
                    "meaning": meanings[0] if meanings else "No translation",
                    "meanings": meanings,
                    "level_new": level_new,
                    "level_old": level_old,
                    "level": level_new or level_old,
                    "frequency": entry.get("frequency", 0),
                    "radical": radical,
                    "is_original_hsk": True,
                }

                if simplified not in hsk_vocab:
                    hsk_vocab[simplified] = new_entry
                    hsk_lists_original[simplified] = new_entry.copy()
                    if level_old:
                        level_num = level_old.replace("old-", "")
                        if level_num in old_level_words:
                            old_level_words[level_num].append(simplified)
                else:
                    existing = hsk_vocab[simplified]
                    # First-occurrence wins on levels; fill in missing ones.
                    best_level_new = existing.get("level_new") or new_entry.get("level_new")
                    best_level_old = existing.get("level_old") or new_entry.get("level_old")
                    existing_meaning = existing.get("meaning", "")
                    new_meaning = new_entry["meaning"]
                    existing_is_bad = "abbr." in existing_meaning or "variant of" in existing_meaning
                    new_is_good = "abbr." not in new_meaning and "variant of" not in new_meaning
                    best_meaning = new_meaning if new_is_good else existing_meaning
                    best_meanings = new_entry["meanings"] if new_is_good else existing.get("meanings", [])
                    best_pinyin = new_entry["pinyin"] if new_is_good else existing.get("pinyin", "")
                    best_radical = new_entry.get("radical") or existing.get("radical", "")
                    merged_entry = {
                        "pinyin": best_pinyin,
                        "meaning": best_meaning,
                        "meanings": best_meanings,
                        "level_new": best_level_new,
                        "level_old": best_level_old,
                        "level": best_level_new or best_level_old,
                        "frequency": max(
                            existing.get("frequency", 0), new_entry.get("frequency", 0)
                        ),
                        "radical": best_radical,
                        "is_original_hsk": True,
                    }
                    hsk_vocab[simplified] = merged_entry
                    hsk_lists_original[simplified] = merged_entry.copy()

                processed += 1

                # Track lowest HSK level per character in both systems.
                for char in simplified:
                    if level_new:
                        level_new_num = int(level_new.replace("new-", "").replace("+", ""))
                        if char not in char_levels_new or level_new_num < char_levels_new[char]:
                            char_levels_new[char] = level_new_num
                    if level_old:
                        level_old_num = int(level_old.replace("old-", ""))
                        if char not in char_levels_old or level_old_num < char_levels_old[char]:
                            char_levels_old[char] = level_old_num

        _add_character_components(char_levels_new, char_levels_old)
        _supplement_missing_levels()

        # Debug breakdown — original HSK vs supplementary entries.
        original_count = sum(1 for w in hsk_vocab.values() if w.get("is_original_hsk", False))
        component_count = sum(
            1 for w in hsk_vocab.values() if not w.get("is_original_hsk", False)
        )
        logger.info(
            f"Vocabulary breakdown: {original_count} original HSK words, "
            f"{component_count} character components/supplemented"
        )

        # Old HSK distribution (original words only) — sanity check.
        old_hsk_dist: dict = {}
        for _word, data in hsk_vocab.items():
            if data.get("level_old") and data.get("is_original_hsk", False):
                level_num = data["level_old"].replace("old-", "")
                old_hsk_dist[level_num] = old_hsk_dist.get(level_num, 0) + 1
        if old_hsk_dist:
            logger.info("OLD HSK distribution (original words only, should match GitHub source):")
            for level in sorted(old_hsk_dist, key=int):
                logger.info(f"  Level {level}: {old_hsk_dist[level]} words")
            logger.info("First 20 words in Old HSK Level 1 (from processing):")
            for i, word in enumerate(old_level_words.get("1", [])[:20]):
                logger.info(f"  {i + 1}. {word}")

        # New HSK distribution (original words only).
        new_hsk_dist: dict = {}
        for _word, data in hsk_vocab.items():
            if data.get("level_new") and data.get("is_original_hsk", False):
                level_num = data["level_new"].replace("new-", "").replace("+", "")
                new_hsk_dist[level_num] = new_hsk_dist.get(level_num, 0) + 1
        if new_hsk_dist:
            logger.info("NEW HSK distribution (original words only):")
            for level in sorted(new_hsk_dist, key=int):
                logger.info(f"  Level {level}: {new_hsk_dist[level]} words")

        _populate_radical_pinyin()
        _combine_multi_char_radicals()
        _apply_konfuzius_old_hsk()
        _save_processed()

        total_chars = len(set(char_levels_new) | set(char_levels_old))
        logger.info(
            f"Processed and saved {processed} HSK words + "
            f"{total_chars} individual characters"
        )
        logger.info(
            f"Level distribution from source: {entries_with_both} with both, "
            f"{entries_with_new_only} new only, {entries_with_old_only} old only "
            f"(out of {total_entries} total entries)"
        )

    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error downloading vocabulary: {e.response.status_code}", exc_info=True
        )
        raise
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.error(f"Network error downloading vocabulary: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error downloading vocabulary: {e}", exc_info=True)
        raise
