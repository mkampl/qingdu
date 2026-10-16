#!/usr/bin/env python3
"""Automatic checks for learner glosses (step 3 of the workflow in
tools/README.md).

Takes either a learner_glosses.json-style file (``{"glosses": {word:
{pinyin, gloss, ...}}}``) or a list of written entries (``[{word, pinyin,
gloss, confidence?, note?}, ...]``) and checks every entry against the
pinned dictionaries, resolved the way the app resolves them.

Hard failures (exit status 1):
- the word is not an HSK word;
- the pinyin is not tone-marked pinyin, or is not the word's main reading
  (the app would skip the gloss);
- the gloss is empty, longer than 40 characters, starts with a register
  tag or a parenthetical ("(bound form) …"), contains Chinese characters
  outside quotes, or is a known-bad headline ("a religion" for 教);
- the same word appears twice (list input).

Flagged for review (reported, exit status unaffected):
- no sense support: none of the gloss's content words occur in a
  CC-CEDICT sense of that reading or in the HSK list's English, after
  lower-casing, dropping stop words and stripping -s/-es/-ed/-ing;
- low confidence, when the entry carries one (below 0.7 or "low").

    python tools/check_learner_glosses.py written-hsk1-2.json
    python tools/check_learner_glosses.py app/data/learner_glosses.json --json report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from learner_gloss_data import (  # noqa: E402
    hsk_list_meaning,
    load_dictionaries,
    main_reading,
    raw_hsk_forms,
)

MAX_GLOSS_CHARS = 40
LOW_CONFIDENCE = 0.7

# Headlines the gloss audit found wrong (notes: translations analysis
# §6b). A learner gloss equal to one of these brings the bug back.
KNOWN_BAD: dict[str, set[str]] = {
    "教": {"a religion"},
    "行": {"capable; competent", "capable"},
    "本": {"originally; initially", "originally"},
    "太": {"highest"},
    "点": {"to touch briefly", "to touch briefly; to tap"},
    "在": {"to exist", "to exist; to be alive"},
    "穿": {"to bore through", "to bore through; to pierce; to perforate"},
    "话": {"dialect"},
    "热": {"to warm up"},
    "跟": {"heel"},
    "关": {"mountain pass"},
    "电": {"lightning"},
    "钱": {"coin"},
    "叫": {"to shout"},
    "次": {"next in sequence"},
    "字": {"letter"},
    "奶": {"breast"},
    "考": {"to check"},
    "课": {"subject"},
    "楼": {"house with more than 1 story"},
    "表": {"exterior surface"},
    "店": {"inn; old-style hotel", "inn"},
    "位": {"position"},
    "条": {"strip"},
    "才": {"ability; talent", "ability"},
    "带": {"band"},
    "层": {"to pile on top of one another"},
    "周": {"to make a circuit"},
    "套": {"to cover"},
    "挺": {"straight"},
    "卡": {"to stop"},
    "封": {"to confer"},
    "度": {"to pass"},
    "当": {"to be"},
    "然": {"correct"},
    "确": {"authenticated"},
    "绩": {"to spin (hemp etc)"},
    "克": {"to be able to"},
    "面": {"flour"},
    "边": {"suffix of a noun of locality"},
    "篇": {"sheet"},
    "响": {"echo"},
    "装": {"adornment"},
    "节": {"joint; node", "joint"},
    "场": {"large place used for a specific purpose"},
    "称": {"to weigh"},
    "汤": {"rushing current"},
    "浅": {"sound of moving water"},
    "薄": {"mint (plant)"},
    "恶心": {"bad habit"},
    "教授": {"to teach (a subject)"},
    "车上": {"car"},
    "送到": {"deliver"},
    "放到": {"put in"},
    "不太": {"not too"},
    "能不能": {"can you"},
    "不一会儿": {"take a short while"},
}

# Pointers and placeholders that are never a learner headline.
_BAD_START_RE = re.compile(
    r"^(see |variant of |old variant of |erhua variant of |used in |abbr\. for |surname )",
    re.IGNORECASE,
)
_LEADING_TAG_RE = re.compile(r"^\s*[(\[]")
# A leading parenthetical is fine when it describes grammar the way a
# vocabulary list does: 个 "(general measure word)", 吗 "(question particle)".
_GRAMMAR_NOTE_RE = re.compile(
    r"^\s*\((?:[^()]*\b(?:measure word|particle|suffix|prefix|action|state)\b[^()]*)\)",
    re.IGNORECASE,
)
_HANZI_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
# Text inside explicit quotes may name Chinese ("the measure word '个'").
_QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'|“[^”]*”|‘[^’]*’|「[^」]*」")

STOPWORDS = {
    "a", "an", "the", "to", "of", "and", "or", "in", "on", "at", "for", "by",
    "with", "from", "as", "be", "is", "are", "sb", "sth", "one's", "it", "its",
    "eg", "etc", "used", "also", "esp", "something", "someone", "somebody",
    "oneself", "very", "not", "up", "out", "off", "into", "about", "that",
    "this", "which", "who", "what", "so",
}  # fmt: skip


def stem(word: str) -> str:
    """Crude English stemmer, applied the same way to gloss and senses so
    teach/teaches/teaching and car/cars meet (irregular forms don't)."""
    w = word.lower().strip("'")
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("ing") and len(w) > 5:
        w = w[:-3]
    elif len(w) > 4 and (w.endswith("ed") or re.search(r"(s|x|z|ch|sh)es$", w)):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        w = w[:-1]
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    # doubled final consonant after stripping -ing/-ed (stopping → stopp)
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiouls":
        w = w[:-1]
    return w


def content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z'-]*", (text or "").lower())
    out = set()
    for raw in words:
        for part in raw.split("-"):
            part = part.strip("'")
            if len(part) < 2 or part in STOPWORDS:
                continue
            out.add(stem(part))
    return out


def is_tone_marked_pinyin(pinyin: str) -> bool:
    from app.services.readings import numbered_syllables

    if not pinyin or any(ch.isdigit() for ch in pinyin):
        return False
    return numbered_syllables(pinyin) is not None


@dataclass
class EntryResult:
    word: str
    pinyin: str
    gloss: str
    errors: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class Context:
    """What the checks need about each word, so they can run on fixtures."""

    hsk_words: set[str]
    main_pinyin: dict[str, str]
    senses: dict[str, list[str]]  # main reading's CC-CEDICT senses
    hsk_english: dict[str, str]
    in_cedict: set[str] = field(default_factory=set)


def build_context(words) -> Context:
    """Context for `words` from the loaded dictionaries."""
    from app import state

    forms = raw_hsk_forms()
    hsk_words = {w for w, e in state.hsk_vocab.items() if e.get("is_original_hsk")}
    main_pinyin, senses, english = {}, {}, {}
    for word in words:
        main = main_reading(word)
        if main:
            main_pinyin[word] = main["pinyin"]
            senses[word] = main["meanings"]
        english[word] = hsk_list_meaning(forms.get(word, []), main_pinyin.get(word))
    in_cedict = {w for w in words if w in state.cedict_vocab}
    return Context(hsk_words, main_pinyin, senses, english, in_cedict)


def check_entry(word: str, item: dict, ctx: Context) -> EntryResult:
    from app.services.learner_glosses import matches_reading

    pinyin = (item.get("pinyin") or "").strip()
    gloss = (item.get("gloss") or "").strip()
    res = EntryResult(word, pinyin, gloss)

    if word not in ctx.hsk_words:
        res.errors.append("not an HSK word")

    main = ctx.main_pinyin.get(word)
    if not is_tone_marked_pinyin(pinyin):
        res.errors.append(f"pinyin {pinyin!r} is not tone-marked pinyin")
    elif main is None:
        res.errors.append("no dictionary reading for this word")
    elif item.get("fixes_hsk_pinyin"):
        # Replaces a broken HSK-list pinyin; only allowed where CC-CEDICT
        # has no entry to take the reading from.
        if word in ctx.in_cedict:
            res.errors.append("fixes_hsk_pinyin on a word CC-CEDICT has")
    elif not matches_reading(pinyin, main):
        res.errors.append(f"pinyin {pinyin!r} is not the main reading {main!r}")

    if not gloss:
        res.errors.append("empty gloss")
        return res
    if len(gloss) > MAX_GLOSS_CHARS:
        res.errors.append(f"gloss longer than {MAX_GLOSS_CHARS} characters ({len(gloss)})")
    if _LEADING_TAG_RE.match(gloss) and not _GRAMMAR_NOTE_RE.match(gloss):
        res.errors.append("gloss starts with a tag or parenthetical")
    if _BAD_START_RE.match(gloss):
        res.errors.append("gloss is a pointer or placeholder")
    if _HANZI_RE.search(_QUOTED_RE.sub("", gloss)):
        res.errors.append("Chinese characters outside quotes")
    if gloss.lower() in {b.lower() for b in KNOWN_BAD.get(word, ())}:
        res.errors.append("known-bad headline")

    gloss_words = content_words(gloss)
    support = set()
    for sense in ctx.senses.get(word, []):
        support |= content_words(sense)
    support |= content_words(ctx.hsk_english.get(word, ""))
    if gloss_words and not gloss_words & support:
        res.flags.append("no sense support")

    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < LOW_CONFIDENCE:
        res.flags.append(f"low confidence ({confidence})")
    elif isinstance(confidence, str) and confidence.strip().lower() == "low":
        res.flags.append("low confidence")
    return res


def read_entries(path: Path) -> list[tuple[str, dict]]:
    """(word, item) pairs from either accepted file shape, in file order."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        glosses = data.get("glosses", data)
        return [(w, item) for w, item in glosses.items() if isinstance(item, dict)]
    if isinstance(data, list):
        return [(str(e.get("word", "")), e) for e in data if isinstance(e, dict)]
    raise ValueError(f"{path}: expected an object with 'glosses' or a list of entries")


def check_entries(entries: list[tuple[str, dict]], ctx: Context) -> list[EntryResult]:
    results = []
    seen: set[str] = set()
    for word, item in entries:
        res = check_entry(word, item, ctx)
        if word in seen:
            res.errors.append("duplicate entry")
        seen.add(word)
        results.append(res)
    return results


def summarize(results: list[EntryResult]) -> dict:
    failed = [r for r in results if r.errors]
    flagged = [r for r in results if r.flags and not r.errors]
    return {
        "total": len(results),
        "ok": sum(1 for r in results if not r.errors and not r.flags),
        "failed": len(failed),
        "flagged": len(flagged),
        "failures": [
            {"word": r.word, "pinyin": r.pinyin, "gloss": r.gloss, "errors": r.errors}
            for r in failed
        ],
        "flagged_entries": [
            {"word": r.word, "pinyin": r.pinyin, "gloss": r.gloss, "flags": r.flags}
            for r in flagged
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file", help="learner_glosses.json or a list of written entries")
    ap.add_argument("--json", metavar="FILE", help="also write the report as JSON")
    args = ap.parse_args(argv)

    entries = read_entries(Path(args.file))
    load_dictionaries()
    ctx = build_context([w for w, _ in entries])
    report = summarize(check_entries(entries, ctx))

    print(
        f"{report['total']} entries: {report['ok']} ok, {report['flagged']} flagged "
        f"for review, {report['failed']} failed"
    )
    for r in report["failures"]:
        print(f"FAIL  {r['word']} {r['pinyin']} {r['gloss']!r}: {'; '.join(r['errors'])}")
    for r in report["flagged_entries"]:
        print(f"FLAG  {r['word']} {r['pinyin']} {r['gloss']!r}: {'; '.join(r['flags'])}")
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
