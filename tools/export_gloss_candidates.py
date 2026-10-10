#!/usr/bin/env python3
"""Export the input for writing learner glosses (step 1 of the workflow in
tools/README.md).

For every HSK headword in the chosen levels, writes what a gloss writer
needs to see, resolved through the app's own loaders on the pinned
dictionary data::

    {
      "word": "教", "level": 1, "main_pinyin": "jiāo",
      "current_headline": "to teach",
      "readings": [{"pinyin", "primary", "meanings", "is_main"}, ...],
      "hsk_list_meaning": "to teach",
      "hsk_list_forms": [{"pinyin", "meanings"}, ...],
      "examples": ["老师教我们写汉字。", ...]
    }

`readings` lists every CC-CEDICT reading with all of its senses, main
reading first (a single item for one-reading words, the HSK list's own
entry for words CC-CEDICT lacks). `current_headline` is what the app shows
today, so it already reflects app/data/learner_glosses.json. `examples` are
up to two sentences from the graded library texts (app/data/library/)
containing the word, short ones (40 characters or fewer) and easier
levels first.

Order: HSK level, then the list's frequency rank, then the word, so the
output is stable for the same data.

    python tools/export_gloss_candidates.py --levels 1-2 -o hsk1-2.json
    python tools/export_gloss_candidates.py --levels 3-4 --hsk-version new -o hsk3-4.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from learner_gloss_data import (  # noqa: E402
    REPO_ROOT,
    hsk_list_meaning,
    level_number,
    load_dictionaries,
    main_reading,
    raw_hsk_forms,
)

LIBRARY_DIR = REPO_ROOT / "app" / "data" / "library"
MAX_EXAMPLES = 2
SHORT_SENTENCE = 40

_SENTENCE_END = set("。！？!?；;…\n")
_SENTENCE_RE = re.compile(r"[^。！？!?；;…\n]+[。！？!?；;…]*")


def parse_levels(spec: str) -> list[int]:
    """ "1-4" → [1, 2, 3, 4]; "1,3" → [1, 3]."""
    levels: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            levels.update(range(lo, hi + 1))
        else:
            levels.add(int(part))
    if not levels:
        raise ValueError(f"no levels in {spec!r}")
    return sorted(levels)


# --- library example sentences ------------------------------------------------


def _sentences_of(text_data: dict) -> list[tuple[str, frozenset[str]]]:
    """(sentence, its token texts) per sentence of a library text. Uses the
    stored segmentation when there is one, else splits the raw text (and
    then only substring matches can find words in it)."""
    words = ((text_data.get("analyzed") or {}).get("words")) or []
    out: list[tuple[str, frozenset[str]]] = []
    if words:
        current: list[str] = []
        for w in words:
            token = w.get("text") or ""
            current.append(token)
            if token and all(ch in _SENTENCE_END for ch in token.strip() or "\n"):
                sentence = "".join(current).strip()
                if sentence:
                    out.append((sentence, frozenset(t.strip() for t in current)))
                current = []
        sentence = "".join(current).strip()
        if sentence:
            out.append((sentence, frozenset(t.strip() for t in current)))
        return out
    for m in _SENTENCE_RE.finditer(text_data.get("text") or ""):
        sentence = m.group(0).strip()
        if sentence:
            out.append((sentence, frozenset()))
    return out


def load_library_sentences(library_dir: Path = LIBRARY_DIR) -> list[dict]:
    """Every sentence of the library texts, in a stable order:
    [{text, tokens, level}]."""
    sentences: list[dict] = []
    seen: set[str] = set()
    for path in sorted(library_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        level = data.get("hsk_level") or 99
        for text, tokens in _sentences_of(data):
            if text in seen:
                continue
            seen.add(text)
            sentences.append({"text": text, "tokens": tokens, "level": level})
    return sentences


def examples_for(word: str, sentences: list[dict], limit: int = MAX_EXAMPLES) -> list[str]:
    """Up to `limit` sentences containing `word` as a token. Words of two
    or more characters also match inside a longer token (older library
    analyses glued some phrases). Short sentences and easier texts first."""
    hits = [s for s in sentences if word in s["tokens"]]
    if len(hits) < limit and len(word) > 1:
        hits += [s for s in sentences if s not in hits and word in s["text"]]
    hits.sort(key=lambda s: (len(s["text"]) > SHORT_SENTENCE, s["level"], len(s["text"])))
    return [s["text"] for s in hits[:limit]]


# --- candidates ---------------------------------------------------------------


def _readings_of(word: str) -> list[dict]:
    from app import state

    cedict = state.cedict_vocab.get(word)
    if cedict and cedict.get("readings"):
        readings = sorted(cedict["readings"], key=lambda r: not r.get("is_main"))
        return [
            {
                "pinyin": r.get("pinyin", ""),
                "primary": r.get("primary", ""),
                "meanings": list(r.get("meanings") or []),
                "is_main": bool(r.get("is_main")),
            }
            for r in readings
        ]
    main = main_reading(word)
    if not main:
        return []
    return [
        {
            "pinyin": main["pinyin"],
            "primary": (main["meanings"] or [""])[0],
            "meanings": main["meanings"],
            "is_main": True,
        }
    ]


def build_candidates(
    levels: list[int], hsk_version: str = "new", sentences: list[dict] | None = None
) -> list[dict]:
    """Candidate records for every original HSK word in `levels`. Expects
    the dictionaries to be loaded already (load_dictionaries)."""
    from app import state
    from app.services.word_info import lookup_pinyin_meaning

    forms = raw_hsk_forms()
    if sentences is None:
        sentences = load_library_sentences()
    wanted = set(levels)
    picked = []
    for word, entry in state.hsk_vocab.items():
        if not entry.get("is_original_hsk"):
            continue
        level = level_number(entry, hsk_version)
        if level in wanted:
            freq = entry.get("frequency") or 0
            picked.append((level, freq if freq > 0 else 10**9, word))
    picked.sort()

    out = []
    for level, _freq, word in picked:
        main = main_reading(word) or {"pinyin": "", "meanings": []}
        _, headline = lookup_pinyin_meaning(word)
        word_forms = forms.get(word, [])
        out.append(
            {
                "word": word,
                "level": level,
                "main_pinyin": main["pinyin"],
                "current_headline": headline,
                "readings": _readings_of(word),
                "hsk_list_meaning": hsk_list_meaning(word_forms, main["pinyin"]),
                "hsk_list_forms": word_forms,
                "examples": examples_for(word, sentences),
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--levels", required=True, help='HSK levels, e.g. "1-4" or "1,2"')
    ap.add_argument(
        "--hsk-version",
        choices=("new", "old"),
        default="new",
        help="which level field to filter on (default: new = HSK 3.0 levels)",
    )
    ap.add_argument("-o", "--output", required=True, help="output JSON file")
    args = ap.parse_args(argv)

    load_dictionaries()
    candidates = build_candidates(parse_levels(args.levels), args.hsk_version)
    Path(args.output).write_text(
        json.dumps(candidates, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    by_level: dict[int, int] = {}
    for c in candidates:
        by_level[c["level"]] = by_level.get(c["level"], 0) + 1
    counts = ", ".join(f"HSK {lvl}: {n}" for lvl, n in sorted(by_level.items()))
    with_examples = sum(1 for c in candidates if c["examples"])
    print(
        f"wrote {len(candidates)} candidates to {args.output} ({counts}; "
        f"{with_examples} with library examples)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
