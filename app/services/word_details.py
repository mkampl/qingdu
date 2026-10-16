"""Measure words and character components for a word.

- Measure words come from the CC-CEDICT reading the app shows for the word
  ("CL:本[ben3],冊|册[ce4]" annotations, which the gloss cleanup drops from
  the meanings), else from the HSK list's own classifiers.
- Components come from Make Me a Hanzi's dictionary.txt (vendored and
  pinned in app/data/dict, LGPL-3.0): each character's decomposition into
  its parts, the parts' meanings, and the etymology hint where there is
  one ("A woman 女 with a son 子").

Both are loaded on first use; nothing here changes how words are glossed,
so dict_version() is not affected.
"""

from __future__ import annotations

import json
import logging
import re
import threading

from app.services import dict_data
from app.services.cedict_loader import _convert_pinyin
from app.services.readings import numbered_syllables
from app.services.word_info import lookup_pinyin_meaning

logger = logging.getLogger(__name__)

_CL_BLOCK_RE = re.compile(r"CL:([^/)]*)")
_CL_ITEM_RE = re.compile(r"(?:[^\s,|\[\]]+\|)?([^\s,|\[\]]+)\[([^\]]+)\]")
# Ideographic description characters (⿰⿱…) and the "unknown part" mark.
_IDC = set("⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻？")
MAX_CLASSIFIERS = 4

_lock = threading.Lock()
_classifiers: dict[tuple[str, str], list[tuple[str, str]]] | None = None
_hsk_classifiers: dict[str, list[str]] | None = None
_chars: dict[str, dict] | None = None


def _load_classifiers() -> None:
    """{(simplified, numbered pinyin lower-case): [(classifier, numbered)]}"""
    global _classifiers, _hsk_classifiers
    out: dict[tuple[str, str], list[tuple[str, str]]] = {}
    found = dict_data.read_vendored("cedict")
    if found:
        for line in found[0].decode("utf-8").splitlines():
            if "CL:" not in line or line.startswith("#"):
                continue
            m = re.match(r"^\S+\s+(\S+)\s+\[([^\]]+)\]\s+/(.+)/\s*$", line)
            if not m:
                continue
            items: list[tuple[str, str]] = []
            for block in _CL_BLOCK_RE.findall(m.group(3)):
                for cl, py in _CL_ITEM_RE.findall(block):
                    if (cl, py) not in items:
                        items.append((cl, py))
            if items:
                out.setdefault((m.group(1), m.group(2).lower()), []).extend(items)
    hsk: dict[str, list[str]] = {}
    found = dict_data.read_vendored("hsk")
    if found:
        for entry in json.loads(found[0]):
            cls = [c for f in entry.get("forms") or [] for c in f.get("classifiers") or []]
            if cls:
                hsk[entry["simplified"]] = list(dict.fromkeys(cls))
    _classifiers, _hsk_classifiers = out, hsk


def _load_chars() -> None:
    global _chars
    out: dict[str, dict] = {}
    found = dict_data.read_vendored("makemeahanzi")
    if found:
        for line in found[0].decode("utf-8").splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            ch = item.get("character")
            if ch:
                out[ch] = item
    else:
        logger.warning("Make Me a Hanzi data missing; no character components")
    _chars = out


def _ensure_loaded() -> None:
    if _classifiers is not None and _chars is not None:
        return
    with _lock:
        if _classifiers is None:
            _load_classifiers()
        if _chars is None:
            _load_chars()


def classifiers(word: str) -> list[dict]:
    """Measure words for the reading the app shows, most common first."""
    _ensure_loaded()
    pinyin, _meaning = lookup_pinyin_meaning(word)
    syl = numbered_syllables(pinyin)
    items: list[tuple[str, str]] = []
    if syl:
        items = list((_classifiers or {}).get((word, " ".join(syl).lower()), []))
    if not items:
        # The reading's line has none: any other CC-CEDICT reading of the
        # word that names one, else the HSK list.
        for (w, _py), cls in (_classifiers or {}).items():
            if w == word:
                items = list(cls)
                break
    out = [{"hanzi": cl, "pinyin": _convert_pinyin(py)} for cl, py in items]
    if not out:
        for cl in (_hsk_classifiers or {}).get(word, []):
            out.append({"hanzi": cl, "pinyin": lookup_pinyin_meaning(cl)[0] or ""})
    return out[:MAX_CLASSIFIERS]


def _char_payload(ch: str) -> dict:
    item = (_chars or {}).get(ch) or {}
    return {
        "char": ch,
        "pinyin": (item.get("pinyin") or [None])[0],
        "definition": item.get("definition"),
    }


def _hint(etym: dict) -> str | None:
    """How the character is built, in a sentence."""
    hint = (etym.get("hint") or "").replace("\xa0", " ").strip() or None
    if etym.get("type") == "pictophonetic":
        semantic, phonetic = etym.get("semantic"), etym.get("phonetic")
        if semantic and phonetic:
            meaning = f" ({hint})" if hint else ""
            return f"{semantic}{meaning} gives the meaning, {phonetic} the sound"
    return hint


def components(word: str) -> list[dict]:
    """Each distinct Chinese character of the word with its parts."""
    _ensure_loaded()
    out: list[dict] = []
    for ch in dict.fromkeys(word):
        item = (_chars or {}).get(ch)
        if not item:
            continue
        parts = [
            _char_payload(p)
            for p in dict.fromkeys(item.get("decomposition") or "")
            if p not in _IDC and p != ch
        ]
        etym = item.get("etymology") or {}
        out.append(
            {
                **_char_payload(ch),
                "decomposition": item.get("decomposition"),
                "parts": parts,
                "radical": item.get("radical"),
                "hint": _hint(etym),
                "kind": etym.get("type"),
            }
        )
    return out


def details(word: str) -> dict:
    return {"word": word, "classifiers": classifiers(word), "characters": components(word)}


__all__ = ["classifiers", "components", "details"]
