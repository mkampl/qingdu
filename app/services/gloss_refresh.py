"""
Bring stored glosses up to the current dictionary.

Saved texts keep the full analyse output in `analysis_data`, and
vocabulary lists keep the pinyin/meaning each word had when it was added,
which may be a machine guess for an isolated token (十点 -> "half-witted")
or a sense the dictionary no longer picks. These helpers re-resolve such
entries from the in-memory dictionaries when `dict_data.dict_version()`
has moved on since the last refresh, and stamp the version they used so
the next open is a no-op.

What is refreshed:
- saved-text tokens whose meaning came from a dictionary (hsk, hsk-chars,
  cedict) or from word-level machine translation. Glossary and package
  tokens are the user's (or the package author's) choice and stay as
  they are. Token text and boundaries are never touched: re-segmenting
  would shift the reading position and the word indices grammar spans
  point at, so segmentation fixes only reach texts that are re-analysed.
- vocabulary-list words the user did not edit, and only when the
  dictionary knows the word (a custom entry with no dictionary match
  keeps whatever it has).

Everything is local; nothing here goes to the network.
"""

from __future__ import annotations

import json
import logging

from pypinyin import Style, lazy_pinyin

from app.core.constants import (
    TRANSLATION_SOURCE_CACHE,
    TRANSLATION_SOURCE_CEDICT,
    TRANSLATION_SOURCE_DEEPL,
    TRANSLATION_SOURCE_GOOGLE,
    TRANSLATION_SOURCE_HSK,
    TRANSLATION_SOURCE_HSK_CHARS,
    TRANSLATION_SOURCE_MYMEMORY,
    TRANSLATION_SOURCE_PARTS,
)
from app.services import dict_data
from app.services.readings import readings_payload
from app.services.word_info import lookup_pinyin_meaning
from app.services.word_lookup import describe_non_word, resolve_from_cedict
from app.state import cedict_vocab, hsk_vocab

logger = logging.getLogger(__name__)

# Key inside a saved text's analysis_data recording the dictionary version
# its glosses were last resolved against.
DICT_VERSION_KEY = "dict_version"

# Token sources that came from the dictionary or from context-free MT and
# can therefore be re-resolved. "unknown" shows up in old rows.
REFRESHABLE_SOURCES = frozenset(
    {
        TRANSLATION_SOURCE_HSK,
        TRANSLATION_SOURCE_HSK_CHARS,
        TRANSLATION_SOURCE_CEDICT,
        TRANSLATION_SOURCE_PARTS,
        TRANSLATION_SOURCE_DEEPL,
        TRANSLATION_SOURCE_GOOGLE,
        TRANSLATION_SOURCE_MYMEMORY,
        TRANSLATION_SOURCE_CACHE,
        "unknown",
    }
)

# Optional per-token fields the analyser emits (the other readings of a
# polyphone, the dictionary parts of a non-word). Copied when the resolved
# entry has them and dropped when it does not, so a stale breakdown never
# lingers.
_OPTIONAL_FIELDS = ("readings", "parts")


def _has_cjk(text: str) -> bool:
    return any("㐀" <= c <= "鿿" or "豈" <= c <= "﫿" for c in text)


def resolve_token(text: str) -> dict:
    """Current gloss fields for one stored token, built the way the
    analyser builds them: the HSK entry, else the CC-CEDICT entry, else the
    token's dictionary parts with no meaning of its own. A token neither
    dictionary lists so loses the per-character glue or machine guess it
    may have been saved with."""
    entry = hsk_vocab.get(text)
    if entry:
        source = {
            "pinyin": entry.get("pinyin", ""),
            "meaning": entry.get("meaning", ""),
            "meanings": entry.get("meanings") or [entry.get("meaning", "")],
            "meaning_tags": entry.get("meaning_tags"),
            "readings": readings_payload(entry),
            "translation_source": TRANSLATION_SOURCE_HSK,
        }
    else:
        source = (
            resolve_from_cedict(text)
            or describe_non_word(text)
            or {
                "pinyin": " ".join(lazy_pinyin(text, style=Style.TONE)),
                "meaning": "",
                "meanings": [],
                "translation_source": TRANSLATION_SOURCE_PARTS,
            }
        )
    info = {
        "pinyin": source.get("pinyin", ""),
        "meaning": source.get("meaning", ""),
        "meanings": source.get("meanings")
        if source.get("meanings") is not None
        else [source.get("meaning", "")],
        "meaning_tags": source.get("meaning_tags") or None,
        "translation_source": source.get("translation_source", TRANSLATION_SOURCE_PARTS),
    }
    for key in _OPTIONAL_FIELDS:
        info[key] = source.get(key) or None
    return info


def _refreshable(word: dict) -> bool:
    if not isinstance(word, dict):
        return False
    if word.get("package_source") or word.get("glossary_source"):
        return False
    if word.get("translation_source") not in REFRESHABLE_SOURCES:
        return False
    text = word.get("text") or ""
    return bool(text) and _has_cjk(text)


def refresh_analysis(analysis_data: dict, version: str | None) -> bool:
    """Re-resolve the dictionary and MT tokens of a stored analysis in
    place. Returns True when the blob changed and should be written back
    (it then carries `version` under DICT_VERSION_KEY).

    Does nothing when `version` is None (dictionaries not fully loaded)
    or the blob was already refreshed against this version."""
    if not version or not isinstance(analysis_data, dict):
        return False
    if analysis_data.get(DICT_VERSION_KEY) == version:
        return False
    cache: dict[str, dict] = {}
    changed = 0
    for word in analysis_data.get("words") or []:
        if not _refreshable(word):
            continue
        text = word["text"]
        info = cache.get(text)
        if info is None:
            info = cache[text] = resolve_token(text)
        for key, value in info.items():
            if value is None:
                if key in word:
                    del word[key]
                    changed += 1
            elif word.get(key) != value:
                word[key] = value
                changed += 1
    analysis_data[DICT_VERSION_KEY] = version
    if changed:
        logger.info("Refreshed %d gloss fields against dictionary %s", changed, version)
    return True


# --- vocabulary lists -------------------------------------------------


def dictionary_meaning(hanzi: str) -> str | None:
    """The meaning the dictionary gives `hanzi`, or None when neither the
    HSK list nor CC-CEDICT knows it."""
    if hanzi not in hsk_vocab and hanzi not in cedict_vocab:
        return None
    return lookup_pinyin_meaning(hanzi)[1]


def is_user_meaning(hanzi: str, meaning: str | None) -> bool:
    """True when `meaning` is something the user typed rather than the
    dictionary gloss, so a later refresh must not overwrite it."""
    meaning = (meaning or "").strip()
    if not meaning:
        return False
    return meaning != (dictionary_meaning(hanzi) or "")


def refresh_list_sections(sections: list, version: str | None) -> int:
    """Refresh pinyin/meaning of every list word without `edited` from the
    dictionary, in place. Words the dictionary does not know keep what
    they have. Returns the number of words that changed."""
    if not version:
        return 0
    changed = 0
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        for word in section.get("words") or []:
            if not isinstance(word, dict) or word.get("edited"):
                continue
            hanzi = (word.get("hanzi") or "").strip()
            if not hanzi or (hanzi not in hsk_vocab and hanzi not in cedict_vocab):
                continue
            pinyin, meaning = lookup_pinyin_meaning(hanzi)
            updates = {"pinyin": pinyin, "meaning": meaning}
            if "meanings" in word:
                entry = hsk_vocab.get(hanzi) or cedict_vocab.get(hanzi) or {}
                updates["meanings"] = entry.get("meanings") or [meaning]
            if any(word.get(k) != v for k, v in updates.items()):
                word.update(updates)
                changed += 1
    return changed


def refresh_vocab_list(db, vocab_list, version: str | None = None) -> bool:
    """Refresh a VocabularyList row's non-edited words when the dictionary
    changed since its last refresh, and persist it. Returns True when the
    row was written."""
    version = version if version is not None else dict_data.dict_version()
    if not version or vocab_list.dict_version == version:
        return False
    try:
        sections = json.loads(vocab_list.sections) if vocab_list.sections else []
    except (TypeError, ValueError):
        return False
    if not isinstance(sections, list):
        return False
    changed = refresh_list_sections(sections, version)
    if changed:
        vocab_list.sections = json.dumps(sections)
        logger.info(
            "Refreshed %d words of vocab list %s against dictionary %s",
            changed,
            vocab_list.id,
            version,
        )
    vocab_list.dict_version = version
    db.commit()
    return True


__all__ = [
    "DICT_VERSION_KEY",
    "REFRESHABLE_SOURCES",
    "dictionary_meaning",
    "is_user_meaning",
    "refresh_analysis",
    "refresh_list_sections",
    "refresh_vocab_list",
    "resolve_token",
]
