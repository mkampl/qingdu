#!/usr/bin/env python3
"""Dictionary diff for word glosses.

Runs the app's own meaning resolver (CC-CEDICT parse -> merge into the HSK
vocabulary -> ``word_info.lookup_pinyin_meaning``) over every HSK entry,
plus optional extra words, and writes a JSON snapshot. Two snapshots taken
before and after a change to sense/reading picking can then be diffed.

Typical use::

    # on main
    python tools/gloss_audit.py snapshot -o /tmp/before.json
    # on the feature branch
    python tools/gloss_audit.py snapshot -o /tmp/after.json
    python tools/gloss_audit.py diff /tmp/before.json /tmp/after.json --level 1 --level 2
    python tools/gloss_audit.py stats /tmp/after.json

Inputs default to the pinned files in ``app/data/dict/`` (the raw upstream
HSK ``complete.json`` and CC-CEDICT, gzip-compressed). ``--hsk`` also takes
an already processed ``hsk_vocabulary.json`` and ``--cedict`` a plain or
gzipped ``cedict_ts.u8``, e.g. copies of the production files.
Nothing is downloaded and nothing is written except the snapshot file.

Snapshot format: ``{word: {pinyin, meaning, meanings, level, original}}``
where ``level`` is the new-HSK level (1-7, 7 = band 7-9) or null, and
``original`` is true for words from the HSK lists (false for supplemented
component characters and ``--words-file`` extras).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DICT_DIR = REPO_ROOT / "app" / "data" / "dict"
DEFAULT_HSK = DICT_DIR / "complete-hsk-vocabulary.json.gz"
DEFAULT_CEDICT = DICT_DIR / "cedict_ts.u8.gz"


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


# --- snapshot ------------------------------------------------------------------


def _level_of(entry: dict) -> int | None:
    m = re.match(r"new-(\d+)", entry.get("level_new") or "")
    return int(m.group(1)) if m else None


def _read_words_file(path: Path) -> list[str]:
    """One word per line (``#`` starts a comment), or a JSON list of words."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        return [str(w).strip() for w in data if str(w).strip()]
    words = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            words.append(line.split()[0])
    return words


def build_snapshot(hsk_path: Path, cedict_path: Path, extra_words: list[str]) -> dict:
    # Imported here so `diff`/`stats` work without the app's dependencies.
    from app import state
    from app.services import cedict_loader
    from app.services.word_info import lookup_pinyin_meaning

    hsk_raw = json.loads(_read_text(hsk_path))
    if isinstance(hsk_raw, list):
        # Raw upstream complete.json: run the app's own processing.
        from app.services.hsk_loader import process_raw_hsk

        process_raw_hsk(hsk_raw)
        hsk_raw = dict(state.hsk_vocab)
    else:
        state.hsk_vocab.clear()
        state.hsk_vocab.update(hsk_raw)
    state.unknown_word_cache.clear()

    parsed = cedict_loader._parse_text(_read_text(cedict_path))
    state.cedict_vocab.clear()
    state.cedict_vocab.update(parsed)
    cedict_loader._merge_into_hsk_vocab()

    snapshot: dict[str, dict] = {}
    for word in hsk_raw:
        pinyin, meaning = lookup_pinyin_meaning(word)
        entry = state.hsk_vocab[word]
        snapshot[word] = {
            "pinyin": pinyin,
            "meaning": meaning,
            "meanings": list(entry.get("meanings") or []),
            "level": _level_of(entry),
            "original": bool(entry.get("is_original_hsk")),
        }
    for word in extra_words:
        if word in snapshot:
            continue
        pinyin, meaning = lookup_pinyin_meaning(word)
        cedict_entry = state.cedict_vocab.get(word) or {}
        snapshot[word] = {
            "pinyin": pinyin,
            "meaning": meaning,
            "meanings": list(cedict_entry.get("meanings") or ([meaning] if meaning else [])),
            "level": None,
            "original": False,
        }
    return snapshot


def cmd_snapshot(args: argparse.Namespace) -> int:
    extra: list[str] = []
    for wf in args.words_file or []:
        extra.extend(_read_words_file(Path(wf)))
    snap = build_snapshot(Path(args.hsk), Path(args.cedict), extra)
    out = Path(args.output)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(snap)} entries to {out}", file=sys.stderr)
    return 0


# --- diff ----------------------------------------------------------------------


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _level_matches(entry: dict, levels: set[int] | None) -> bool:
    return levels is None or entry.get("level") in levels


def diff_snapshots(before: dict, after: dict, levels: set[int] | None = None) -> dict:
    groups: dict[str, list] = {
        "added": [],
        "removed": [],
        "pinyin": [],
        "headline": [],
        "list": [],
    }
    for word in sorted(set(before) | set(after)):
        a, b = before.get(word), after.get(word)
        ref = b if b is not None else a
        if not _level_matches(ref, levels):
            continue
        if a is None:
            groups["added"].append((word, None, b))
            continue
        if b is None:
            groups["removed"].append((word, a, None))
            continue
        if a.get("pinyin") != b.get("pinyin"):
            groups["pinyin"].append((word, a, b))
        if a.get("meaning") != b.get("meaning"):
            groups["headline"].append((word, a, b))
        elif a.get("meanings") != b.get("meanings"):
            # Only list-order/content changes that leave the headline alone;
            # headline changes are already reported above.
            groups["list"].append((word, a, b))
    return groups


def _fmt_level(entry: dict | None) -> str:
    lvl = (entry or {}).get("level")
    return f"HSK{lvl}" if lvl else "-"


def cmd_diff(args: argparse.Namespace) -> int:
    before, after = _load(args.before), _load(args.after)
    levels = set(args.level) if args.level else None
    groups = diff_snapshots(before, after, levels)
    limit = args.limit
    titles = {
        "pinyin": "Pinyin changes",
        "headline": "Headline (primary meaning) changes",
        "list": "Meaning-list changes (headline unchanged)",
        "added": "Added entries",
        "removed": "Removed entries",
    }
    for key in ("pinyin", "headline", "list", "added", "removed"):
        rows = groups[key]
        print(f"## {titles[key]}: {len(rows)}")
        for word, a, b in rows[: limit or None]:
            lvl = _fmt_level(b or a)
            if key == "pinyin":
                print(f"  {word} [{lvl}]  {a['pinyin']}  ->  {b['pinyin']}")
            elif key == "headline":
                print(f"  {word} [{lvl}]  {a['meaning']!r}  ->  {b['meaning']!r}")
            elif key == "list":
                print(f"  {word} [{lvl}]")
                print(f"      - {a['meanings']}")
                print(f"      + {b['meanings']}")
            else:
                e = b or a
                print(f"  {word} [{lvl}]  {e['pinyin']}  {e['meaning']!r}")
        if limit and len(rows) > limit:
            print(f"  ... {len(rows) - limit} more")
        print()
    total = sum(len(v) for v in groups.values())
    print(
        "summary: "
        + ", ".join(f"{k}={len(v)}" for k, v in groups.items())
        + f" (total {total}"
        + (f", levels {sorted(levels)}" if levels else "")
        + ")"
    )
    return 1 if args.exit_code and total else 0


# --- stats ---------------------------------------------------------------------

# Heuristic flags from the gloss audit. They have false positives; use them
# to compare runs, not as a list of bugs.
_FLAGS = {
    "ui-tone-mark": lambda p, m, ms: re.search(r"[ūúǔù]i", p) is not None,
    "register-tag-headline": lambda p, m, ms: (
        re.match(
            r"(?i)\((bound form|literary|classical|archaic|dialect|old|coll\.|tcm|slang|vulgar)\)",
            m,
        )
        is not None
    ),
    "classifier-headline": lambda p, m, ms: (
        re.search(r"\bclassifier\b|measure word", m, re.I) is not None
    ),
    "abbr-headline": lambda p, m, ms: "abbr." in m.lower(),
    "affix-headline": lambda p, m, ms: re.search(r"(?i)\bsuffix\b|\bprefix\b|^-|^~", m) is not None,
    "variant/see-headline": lambda p, m, ms: (
        re.match(r"(?i)(erhua |old |unofficial )?(variant|form) of|used in|see ", m) is not None
    ),
    "long/truncated": lambda p, m, ms: m.endswith("…") or len(m) > 60,
    "meaning!=meanings[0]": lambda p, m, ms: bool(ms) and bool(m) and ms[0] != m,
    "glued-compound": lambda p, m, ms: " + " in m,
    "empty-meaning": lambda p, m, ms: not m,
}


def cmd_stats(args: argparse.Namespace) -> int:
    snap = _load(args.snapshot)
    levels = set(args.level) if args.level else None
    groups = {"original": Counter(), "other": Counter()}
    sizes = Counter()
    examples: dict[str, list[str]] = {}
    for word, e in snap.items():
        if not _level_matches(e, levels):
            continue
        group = "original" if e.get("original") else "other"
        sizes[group] += 1
        p, m, ms = e.get("pinyin") or "", e.get("meaning") or "", e.get("meanings") or []
        for name, fn in _FLAGS.items():
            if fn(p, m, ms):
                groups[group][name] += 1
                examples.setdefault(name, [])
                if len(examples[name]) < 8:
                    examples[name].append(word)
    print(
        f"entries: {sum(sizes.values())} (original HSK {sizes['original']}, other {sizes['other']})"
    )
    for name in _FLAGS:
        o, x = groups["original"][name], groups["other"][name]
        print(
            f"  {name:24s} original={o:<6d} other={x:<6d} e.g. {' '.join(examples.get(name, []))}"
        )
    return 0


# --- CLI -----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="resolve every word and write a JSON snapshot")
    s.add_argument(
        "--hsk",
        default=str(DEFAULT_HSK),
        help="complete.json[.gz] or processed hsk_vocabulary.json (default: %(default)s)",
    )
    s.add_argument(
        "--cedict", default=str(DEFAULT_CEDICT), help="cedict_ts.u8[.gz] (default: %(default)s)"
    )
    s.add_argument(
        "--words-file",
        action="append",
        help="extra words, one per line or a JSON list (repeatable)",
    )
    s.add_argument("-o", "--output", required=True, help="snapshot file to write")
    s.set_defaults(func=cmd_snapshot)

    d = sub.add_parser("diff", help="compare two snapshots")
    d.add_argument("before")
    d.add_argument("after")
    d.add_argument("--level", type=int, action="append", help="only this HSK level (repeatable)")
    d.add_argument("--limit", type=int, default=0, help="max rows printed per group (0 = all)")
    d.add_argument("--exit-code", action="store_true", help="exit 1 if anything changed")
    d.set_defaults(func=cmd_diff)

    st = sub.add_parser("stats", help="heuristic flag counts for one snapshot")
    st.add_argument("snapshot")
    st.add_argument("--level", type=int, action="append", help="only this HSK level (repeatable)")
    st.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
