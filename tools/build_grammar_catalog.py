#!/usr/bin/env python3
"""Build app/data/grammar/catalog.json from the HSK 3.0 grammar list.

    LLM_BASE_URL=… LLM_MODEL=… [LLM_API_KEY=…] [LLM_EXTRA_BODY=…] \\
        python3 tools/build_grammar_catalog.py [--limit N]

Reads app/data/grammar/hsk30-grammar.csv (the 573 points of the HSK 3.0
grammar syllabus, see LICENSE-hsk30-grammar.txt) and drafts, for each
point, what the grammar section shows: an English title, a short
explanation for a learner, the structure, two example sentences at that
level, and three words to offer as wrong choices in a gap exercise. The
drafts come from the LLM configured like the app's own (any
OpenAI-compatible endpoint); every draft is checked here (the example
must use one of the point's words) and the result is committed, so the
app itself needs no LLM for the catalog. Already drafted points are kept,
so the tool can be stopped and run again; --redo IDS drafts those again.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import llm  # noqa: E402

SRC = ROOT / "app" / "data" / "grammar" / "hsk30-grammar.csv"
OUT = ROOT / "app" / "data" / "grammar" / "catalog.json"
BATCH = 5
PARALLEL = 4
CJK = re.compile(r"[㐀-鿿]+")

SCHEMA = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "no": {"type": "integer"},
                    "title_en": {"type": "string"},
                    "explanation": {"type": "string"},
                    "structure": {"type": "string"},
                    "examples": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"zh": {"type": "string"}, "en": {"type": "string"}},
                            "required": ["zh", "en"],
                        },
                    },
                    "distractors": {"type": "array", "items": {"type": "string"}},
                    "markers": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "no",
                    "title_en",
                    "explanation",
                    "structure",
                    "examples",
                    "distractors",
                    "markers",
                ],
            },
        }
    },
    "required": ["points"],
}

PROMPT = """You write a grammar reference for learners of Chinese, in English.
For each point of the official HSK 3.0 grammar syllabus below, give:
- title_en: a short English name (max 60 characters), e.g. "把 sentence: doing something to an object"
- explanation: 1-3 plain sentences for a learner at that level: what it means and how it is used (max 300 characters)
- structure: the pattern as a formula, e.g. "Subject + 把 + Object + Verb + Other"
- examples: two natural example sentences in simplified Chinese at that HSK level that clearly use this point, each with an English translation
- distractors: three Chinese words a learner could confuse with the point's key word, for a fill-the-gap exercise (not correct in its place)
- markers: the Chinese words of the point that literally appear in a sentence using it, taken from its forms (for 既然……，就…… ["既然", "就"]; for 才1、都2 ["才", "都"]); an empty list when the point is a sentence structure without fixed words (subject, predicate, 连动句 …)
Numbers after words (了1, 都2) only tell senses apart in the syllabus; never write them in the examples.

Points (no | level | group | category | details | forms):
{points}
"""


def syllabus_words(row: dict) -> list[str]:
    """The Chinese words of a point (its forms), for finding candidate
    sentences: 既然……，就…… -> [既然, 就]; 才1、都2 -> [才, 都]."""
    text = " ".join(row[k] for k in ("Category", "Details", "Content"))
    text = re.sub(r"\d", "", text)
    words = []
    for w in CJK.findall(text):
        if len(w) <= 4 and w not in words:
            words.append(w)
    return words


def point_markers(row: dict, draft: dict) -> list[str]:
    """The draft's markers that the syllabus really lists for the point."""
    text = re.sub(r"\d", "", " ".join(row[k] for k in ("Category", "Details", "Content")))
    out = []
    for m in draft.get("markers") or []:
        m = re.sub(r"\d", "", m.strip())
        if m and CJK.fullmatch(m) and m in text and m not in out:
            out.append(m)
    return out


def forms(row: dict) -> str:
    """How the point is written in the syllabus, for display."""
    parts = [row["Category"], row["Details"], row["Content"]]
    return " · ".join(re.sub(r"\s+", " ", p).strip() for p in parts if p.strip())


def check(row: dict, draft: dict) -> list[str]:
    """Problems with a draft; empty when it can be used."""
    problems = []
    if not (draft.get("title_en") or "").strip():
        problems.append("no title")
    if not (draft.get("explanation") or "").strip():
        problems.append("no explanation")
    examples = [e for e in draft.get("examples") or [] if CJK.search(e.get("zh") or "")]
    if len(examples) < 2:
        problems.append("fewer than two examples")
    keys = point_markers(row, draft)
    if keys and examples and not any(any(k in e["zh"] for k in keys) for e in examples):
        problems.append("examples use none of the point's words")
    # A syllabus sense number copied into an example (了1); dates and
    # times (2024年5月, 3点) are fine.
    raw = " ".join(row[k] for k in ("Category", "Details", "Content"))
    words = set(re.findall(r"([\u3400-\u9fff]+)\d", raw))
    if any(re.search(re.escape(w) + r"\d", e.get("zh") or "") for w in words for e in examples):
        problems.append("sense number in an example")
    return problems


async def draft(rows: list[dict]) -> dict[int, dict]:
    listing = "\n".join(
        " | ".join(
            [r["No"], r["Level"], r["Group"], r["Category"], r["Details"]]
            + [re.sub(r"\s+", " ", r["Content"])]
        )
        for r in rows
    )
    reply = await llm.chat(
        [{"role": "user", "content": PROMPT.format(points=listing)}],
        schema=SCHEMA,
        max_tokens=3000,
        temperature=0.3,
        timeout=180,
    )
    return {int(p["no"]): p for p in reply.get("points", []) if str(p.get("no", "")).isdigit()}


def entry(row: dict, d: dict) -> dict:
    return {
        "id": f"hsk30-{int(row['No']):03d}",
        "no": int(row["No"]),
        "level": row["Level"],
        "group": row["Group"],
        "category": row["Category"],
        "details": row["Details"],
        "forms": forms(row),
        "markers": point_markers(row, d),
        "title_en": d["title_en"].strip()[:80],
        "explanation": d["explanation"].strip()[:400],
        "structure": d["structure"].strip()[:160],
        "examples": [{"zh": e["zh"].strip(), "en": e["en"].strip()} for e in d["examples"][:2]],
        # A wrong choice must not be one of the point's own words.
        "distractors": [
            w.strip()
            for w in d.get("distractors") or []
            if w.strip() and w.strip() not in syllabus_words(row) and CJK.fullmatch(w.strip())
        ][:3],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="draft at most N points this run")
    ap.add_argument("--redo", default="", help="comma list of point numbers to draft again")
    args = ap.parse_args()
    if llm.config() is None:
        raise SystemExit("Set LLM_BASE_URL and LLM_MODEL (see .env.example).")

    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    done: dict[int, dict] = {}
    if OUT.exists():
        done = {e["no"]: e for e in json.loads(OUT.read_text(encoding="utf-8"))["entries"]}
    for no in [int(x) for x in args.redo.split(",") if x.strip()]:
        done.pop(no, None)
    todo = [r for r in rows if int(r["No"]) not in done]
    if args.limit:
        todo = todo[: args.limit]

    async def run(batch: list[dict]) -> None:
        for _attempt in range(2):
            try:
                drafts = await draft(batch)
            except llm.LlmError as e:
                print("LLM error:", e, file=sys.stderr)
                drafts = {}
            missing = []
            for row in batch:
                d = drafts.get(int(row["No"]))
                problems = check(row, d) if d else ["no draft"]
                if problems:
                    missing.append(row)
                    print(f"  {row['No']}: {', '.join(problems)}", file=sys.stderr)
                else:
                    done[int(row["No"])] = entry(row, d)
            if not missing:
                return
            batch = missing

    # Several batches at a time (LLM_CONCURRENCY caps how many run at once).
    batches = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
    for i in range(0, len(batches), PARALLEL):
        await asyncio.gather(*(run(b) for b in batches[i : i + PARALLEL]))
        save(rows, done)
        print(f"{len(done)}/{len(rows)} drafted", file=sys.stderr)


def save(rows: list[dict], done: dict[int, dict]) -> None:
    entries = [done[int(r["No"])] for r in rows if int(r["No"]) in done]
    OUT.write_text(
        json.dumps(
            {
                "_about": (
                    "Grammar catalog of the grammar section: the points of the HSK 3.0 grammar "
                    "syllabus (hsk30-grammar.csv, MIT, see LICENSE-hsk30-grammar.txt) with English "
                    "titles, explanations, structures, examples and gap-exercise distractors "
                    "drafted by tools/build_grammar_catalog.py and checked by it."
                ),
                "version": 1,
                "entries": entries,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
