"""Shared helpers for the learner-gloss tools (export_gloss_candidates.py,
check_learner_glosses.py): load the pinned dictionaries the way the app
does, and read what the raw HSK list says about each word.

Not a script; see tools/README.md for the workflow.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_dictionaries() -> None:
    """Fill `hsk_vocab` / `cedict_vocab` from app/data/dict/ exactly as
    startup does (reading anchoring, overrides and the current
    learner_glosses.json included)."""
    from app.services import dict_data

    dict_data.load_pinned_dictionaries()


def raw_hsk_forms() -> dict[str, list[dict]]:
    """{word: [{pinyin, meanings}]} from the vendored raw HSK list, one item
    per form the list gives (教 has jiāo "to teach" and jiào "religion…")."""
    from app.services import dict_data

    vendored = dict_data.read_vendored("hsk")
    if vendored is None:
        return {}
    out: dict[str, list[dict]] = {}
    for entry in json.loads(vendored[0]):
        word = entry.get("simplified") if isinstance(entry, dict) else None
        if not word:
            continue
        forms = out.setdefault(word, [])
        for form in entry.get("forms") or []:
            item = {
                "pinyin": (form.get("transcriptions") or {}).get("pinyin", ""),
                "meanings": list(form.get("meanings") or []),
            }
            if item not in forms:
                forms.append(item)
    return out


def level_number(entry: dict, version: str = "new") -> int | None:
    """HSK level as an int from `level_new` ("new-3") or `level_old`."""
    m = re.match(rf"{version}-(\d+)", entry.get(f"level_{version}") or "")
    return int(m.group(1)) if m else None


def main_reading(word: str) -> dict | None:
    """{pinyin, meanings} of the word's main reading as the app resolves
    it: the anchored CC-CEDICT reading, or the HSK list's own entry for a
    word CC-CEDICT lacks. `meanings` are always the source's senses, never
    a learner gloss."""
    from app import state

    cedict = state.cedict_vocab.get(word)
    if cedict and cedict.get("readings"):
        main = next((r for r in cedict["readings"] if r.get("is_main")), cedict["readings"][0])
        return {"pinyin": main.get("pinyin", ""), "meanings": list(main.get("meanings") or [])}
    if cedict:
        return {"pinyin": cedict.get("pinyin", ""), "meanings": list(cedict.get("meanings") or [])}
    hsk = state.hsk_lists_original.get(word) or state.hsk_vocab.get(word)
    if hsk:
        return {"pinyin": hsk.get("pinyin", ""), "meanings": list(hsk.get("meanings") or [])}
    return None


def hsk_list_meaning(forms: list[dict], main_pinyin: str | None) -> str:
    """The HSK list's English for the form matching the main reading, or
    for every form when none matches (all forms' senses, "; "-joined)."""
    from app.services.learner_glosses import matches_reading

    matching = [f for f in forms if main_pinyin and matches_reading(f["pinyin"], main_pinyin)]
    chosen = matching or forms
    seen: list[str] = []
    for form in chosen:
        for m in form["meanings"]:
            if m not in seen:
                seen.append(m)
    return "; ".join(seen)
