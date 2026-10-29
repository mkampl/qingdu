"""
Split user words that are not dictionary words into their parts.

A database can hold user words for phrases such as 很多 or 洗衣服, with a
glued "very + many" gloss. This finds those rows (multi-character Chinese words that are not in HSK, CC-CEDICT, the
user's own vocabulary lists or a package gloss) and, for each:

- splits the word into dictionary words (洗衣服 -> 洗 + 衣服, 我来 -> 我 + 来);
  single characters count as parts too;
- leaves a part alone when the user already has a row for it (state and
  schedule untouched);
- creates a missing part as a copy of the glued row's state and schedule,
  with pinyin and meaning from the dictionary;
- deletes the glued row and its glosses. Its user_word_events stay.

It is run by hand, dry run first, never at startup:

    python -m app.services.glue_migration --db /app/data/qingdu.db
    python -m app.services.glue_migration --db /app/data/qingdu.db --apply

Running it again finds nothing left to do.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.services.lexicon import (
    dictionaries_loaded,
    in_dictionary,
    is_cjk_word,
    split_into_known,
)
from app.services.word_info import lookup_pinyin_meaning

logger = logging.getLogger(__name__)

# Copied from the glued row onto parts that are created for it.
COPIED_FIELDS = (
    "state",
    "seen_count",
    "ease",
    "stability",
    "difficulty",
    "fsrs_state",
    "due_at",
    "last_reviewed_at",
    "modes_completed",
    "modes_cycle_started_at",
    "created_at",
)


@dataclass
class PartPlan:
    word: str
    # "exists": the user already has this word, it is left as it is.
    # "create": a new row copying the glued row's state and schedule.
    action: str
    state: str
    pinyin: str = ""
    meaning: str = ""
    # For "exists" parts created earlier in the same run (two glued rows
    # sharing a part): the glued word whose copy wins.
    created_for: str | None = None


@dataclass
class RowPlan:
    user_id: int
    username: str
    row_id: int
    word: str
    state: str
    meaning: str
    parts: list[PartPlan] = field(default_factory=list)
    _row: dict = field(default_factory=dict, repr=False)


def _own_words(conn: sqlite3.Connection, user_id: int) -> set[str]:
    """The user's vocabulary-list entries and package-glossed words."""
    words: set[str] = set()
    for (sections,) in conn.execute(
        "SELECT sections FROM vocabulary_lists WHERE user_id = ?", (user_id,)
    ):
        try:
            parsed = json.loads(sections) if sections else []
        except (TypeError, ValueError):
            continue
        for section in parsed or []:
            for entry in (section or {}).get("words") or []:
                hanzi = (entry.get("hanzi") or "").strip() if isinstance(entry, dict) else ""
                if hanzi:
                    words.add(hanzi)
    for (word,) in conn.execute(
        """
        SELECT DISTINCT uw.word FROM user_words uw
        LEFT JOIN user_word_glosses g ON g.user_word_id = uw.id
        WHERE uw.user_id = ? AND (g.source = 'package' OR uw.meaning_source = 'package')
        """,
        (user_id,),
    ):
        words.add(word)
    return words


def is_glued(word: str, own: set[str]) -> bool:
    return len(word) > 1 and is_cjk_word(word) and not in_dictionary(word) and word not in own


def plan(conn: sqlite3.Connection) -> list[RowPlan]:
    """Work out what `apply` would do. Reads only."""
    if not dictionaries_loaded():
        raise RuntimeError("HSK and CC-CEDICT must be loaded to tell words from phrases")
    conn.row_factory = sqlite3.Row
    users = {r["id"]: r["username"] for r in conn.execute("SELECT id, username FROM users")}
    rows = [dict(r) for r in conn.execute("SELECT * FROM user_words ORDER BY user_id, id")]

    by_user: dict[int, dict[str, dict]] = {}
    for r in rows:
        by_user.setdefault(r["user_id"], {})[r["word"]] = r

    plans: list[RowPlan] = []
    for user_id, words in by_user.items():
        own = _own_words(conn, user_id)
        planned: dict[str, str] = {}  # part created in this run -> glued word
        for word, r in words.items():
            if not is_glued(word, own):
                continue
            rp = RowPlan(
                user_id=user_id,
                username=users.get(user_id, f"#{user_id}"),
                row_id=r["id"],
                word=word,
                state=r["state"],
                meaning=r.get("meaning") or "",
                _row=r,
            )
            for part in split_into_known(word, own):
                pinyin, meaning = lookup_pinyin_meaning(part)
                # Parts are dictionary words or single characters, never
                # glued rows themselves.
                if part in words:
                    rp.parts.append(PartPlan(part, "exists", words[part]["state"]))
                elif part in planned:
                    rp.parts.append(
                        PartPlan(
                            part,
                            "exists",
                            words[planned[part]]["state"],
                            created_for=planned[part],
                        )
                    )
                else:
                    planned[part] = word
                    rp.parts.append(PartPlan(part, "create", r["state"], pinyin, meaning))
            plans.append(rp)
    return plans


def apply(conn: sqlite3.Connection, plans: list[RowPlan]) -> dict:
    """Carry out `plans` in one transaction. Returns counts."""
    now = datetime.utcnow().isoformat(sep=" ")
    created = deleted = 0
    with conn:
        for rp in plans:
            for part in rp.parts:
                if part.action != "create":
                    continue
                taken = conn.execute(
                    "SELECT 1 FROM user_words WHERE user_id = ? AND word = ?",
                    (rp.user_id, part.word),
                ).fetchone()
                if taken:
                    continue
                values = {f: rp._row.get(f) for f in COPIED_FIELDS}
                values["modes_completed"] = values["modes_completed"] or "[]"
                values.update(
                    user_id=rp.user_id,
                    word=part.word,
                    pinyin=part.pinyin or None,
                    meaning=part.meaning or None,
                    meaning_source="dictionary",
                    updated_at=now,
                )
                cols = ", ".join(values)
                marks = ", ".join("?" for _ in values)
                cur = conn.execute(
                    f"INSERT INTO user_words ({cols}) VALUES ({marks})", tuple(values.values())
                )
                if part.meaning:
                    conn.execute(
                        "INSERT INTO user_word_glosses"
                        " (user_word_id, pinyin, meaning, source, source_tag, created_at)"
                        " VALUES (?, ?, ?, 'dictionary', NULL, ?)",
                        (cur.lastrowid, part.pinyin or None, part.meaning, now),
                    )
                created += 1
                logger.info(
                    "user %s: created %s (%s) for %s", rp.user_id, part.word, part.state, rp.word
                )
            conn.execute("DELETE FROM user_word_glosses WHERE user_word_id = ?", (rp.row_id,))
            conn.execute("DELETE FROM user_words WHERE id = ?", (rp.row_id,))
            deleted += 1
            logger.info("user %s: deleted %s (%s)", rp.user_id, rp.word, rp.state)
    return {"glued_rows_deleted": deleted, "part_rows_created": created}


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


def format_table(plans: list[RowPlan]) -> str:
    if not plans:
        return "No glued user words found."
    header = ("user", "glued word", "state", "parts")
    body = []
    for rp in plans:
        cells = []
        for p in rp.parts:
            if p.action == "create":
                cells.append(f"{p.word} (create: {p.state})")
            elif p.created_for:
                cells.append(f"{p.word} (exists: {p.state}, created for {p.created_for})")
            else:
                cells.append(f"{p.word} (exists: {p.state})")
        body.append((rp.username, rp.word, rp.state, ", ".join(cells)))
    widths = [max(_width(row[i]) for row in (header, *body)) for i in range(3)]

    def line(row) -> str:
        return "  ".join(_pad(row[i], widths[i]) for i in range(3)) + "  " + row[3]

    lines = [line(header), line(tuple("-" * w for w in widths) + ("-----",))]
    lines.extend(line(row) for row in body)
    n_create = sum(p.action == "create" for rp in plans for p in rp.parts)
    n_exists = len([p for rp in plans for p in rp.parts]) - n_create
    lines.append("")
    lines.append(
        f"{len(plans)} glued rows -> delete; {n_create} part rows to create; "
        f"{n_exists} parts already present (left untouched)"
    )
    return "\n".join(lines)


def to_json(plans: list[RowPlan]) -> list[dict]:
    out = []
    for rp in plans:
        d = asdict(rp)
        d.pop("_row", None)
        out.append(d)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Split user words that are not dictionary words into their parts."
    )
    parser.add_argument("--db", required=True, help="path to qingdu.db")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="show the plan only (default)")
    mode.add_argument("--apply", action="store_true", help="carry out the plan")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    logging.getLogger("app.services.hsk_loader").setLevel(logging.WARNING)
    logging.getLogger("app.services.cedict_loader").setLevel(logging.WARNING)

    from app.services.dict_data import load_pinned_dictionaries

    load_pinned_dictionaries()
    conn = sqlite3.connect(args.db)
    try:
        plans = plan(conn)
        if args.json:
            print(json.dumps(to_json(plans), ensure_ascii=False, indent=1))
        else:
            print(format_table(plans))
        if args.apply:
            result = apply(conn, plans)
            print(json.dumps(result), file=sys.stderr)
        elif plans:
            print(
                "\nDry run: nothing changed. Re-run with --apply to carry it out.", file=sys.stderr
            )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
