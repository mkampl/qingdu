"""
Learner glosses: a reviewed short headline per HSK word.

CC-CEDICT orders senses etymology first, so even with the right reading
its first usable sense is often not what a learner meets first (太
"highest", 点 "to touch briefly", 话 "dialect"). `app/data/learner_glosses.json`
holds a short learner gloss per word, tied to the reading it was written
for:

    {"glosses": {"太": {"pinyin": "tài", "gloss": "too; very", "source": "reviewed"}}}

It runs after the main reading is picked (app.services.readings) and
replaces only the headline: the main reading's `primary` and therefore the
entry's `meaning`. The CC-CEDICT senses (`meanings`) and the other
readings stay as they are, so the popover and the review card still show
them under the headline. A gloss whose `pinyin` no longer matches the
main reading (a dictionary refresh or reading override moved it) is
skipped with a warning rather than put on the wrong reading.

The file is one of the dictionary rule files (`dict_data._RULE_FILES`), so
editing it changes `dict_version()` and refreshes user-word snapshots.
How the file is written and checked: see tools/README.md.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services import readings as readings_service

logger = logging.getLogger(__name__)

LEARNER_GLOSSES_FILE = Path(__file__).resolve().parent.parent / "data" / "learner_glosses.json"


def load_learner_glosses(path: Path | None = None) -> dict[str, dict]:
    """{word: {"pinyin", "gloss", ...}} from the learner-gloss file. Entries
    without a pinyin or a gloss are dropped. Missing or broken file → {}."""
    path = path or LEARNER_GLOSSES_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logger.error("Unreadable learner glosses %s: %s", path, e)
        return {}
    out: dict[str, dict] = {}
    for word, item in (data.get("glosses") or {}).items():
        if not isinstance(item, dict):
            continue
        pinyin = (item.get("pinyin") or "").strip()
        gloss = (item.get("gloss") or "").strip()
        if pinyin and gloss:
            out[word] = {**item, "pinyin": pinyin, "gloss": gloss}
    return out


def matches_reading(gloss_pinyin: str, reading_pinyin: str | None) -> bool:
    """Same syllables and tones, spacing and case aside."""
    return (
        readings_service.match_strength(
            readings_service.numbered_syllables(gloss_pinyin),
            readings_service.numbered_syllables(reading_pinyin),
        )
        == readings_service.STRONG_MATCH
    )


def apply_to_parsed(parsed: dict[str, dict], glosses: dict[str, dict]) -> int:
    """Put the learner gloss on the main reading of each CC-CEDICT entry
    in `parsed` (before the top-level fields are synced from it). The
    reading's register tags go too: they belonged to the CC-CEDICT sense
    the gloss replaces. Returns how many entries changed."""
    applied = 0
    for word, item in glosses.items():
        entry = parsed.get(word)
        if not entry or not entry.get("readings"):
            continue
        main = next((r for r in entry["readings"] if r.get("is_main")), entry["readings"][0])
        if not matches_reading(item["pinyin"], main.get("pinyin")):
            logger.warning(
                "Learner gloss for %s is for %s, main reading is %s; skipped",
                word,
                item["pinyin"],
                main.get("pinyin"),
            )
            continue
        main["primary"] = item["gloss"]
        main["meaning_tags"] = []
        applied += 1
    return applied


def apply_to_hsk_only(word: str, hsk_entry: dict, glosses: dict[str, dict]) -> bool:
    """Same for an HSK word CC-CEDICT does not have: its headline is the
    HSK list's own English, matched against the list's pinyin."""
    item = glosses.get(word)
    if not item:
        return False
    if not matches_reading(item["pinyin"], hsk_entry.get("pinyin")):
        logger.warning(
            "Learner gloss for %s is for %s, HSK pinyin is %s; skipped",
            word,
            item["pinyin"],
            hsk_entry.get("pinyin"),
        )
        return False
    hsk_entry["meaning"] = item["gloss"]
    hsk_entry["meaning_tags"] = []
    return True


__all__ = [
    "LEARNER_GLOSSES_FILE",
    "apply_to_hsk_only",
    "apply_to_parsed",
    "load_learner_glosses",
    "matches_reading",
]
