"""
Personal-data exports — CSV of all your word states, and an Anki deck
of the words you're currently learning. Both are user-scoped via
require_auth (and the iframe-tolerant flexible variant for the download
links so they work without setting Authorization headers).
"""

from __future__ import annotations

import contextlib
import csv
import io
import logging
import os
import tempfile

import genanki
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_auth, require_auth_flexible
from app.database import User, UserWord, get_db
from app.state import hsk_vocab

router = APIRouter(tags=["Export"])
logger = logging.getLogger(__name__)


_CSV_FIELDS = [
    "word",
    "state",
    "pinyin",
    "meaning",
    "hsk_level",
    "seen_count",
    "stability",
    "difficulty",
    "due_at",
    "last_reviewed_at",
    "created_at",
]


@router.get("/api/words/export.csv")
async def export_words_csv(
    user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db),
):
    """All UserWord rows for the current user as CSV. Streams in memory —
    even a few-thousand-row export comes in well under 1 MB."""
    rows = (
        db.query(UserWord)
        .filter(UserWord.user_id == user.id)
        .order_by(UserWord.created_at.asc())
        .all()
    )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for r in rows:
        entry = hsk_vocab.get(r.word, {}) or {}
        writer.writerow(
            {
                "word": r.word,
                "state": r.state,
                "pinyin": entry.get("pinyin", ""),
                "meaning": entry.get("meaning", ""),
                "hsk_level": entry.get("level", ""),
                "seen_count": r.seen_count or 0,
                "stability": r.stability if r.stability is not None else "",
                "difficulty": r.difficulty if r.difficulty is not None else "",
                "due_at": r.due_at.isoformat() if r.due_at else "",
                "last_reviewed_at": r.last_reviewed_at.isoformat() if r.last_reviewed_at else "",
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="qingdu-words-{user.username}.csv"',
            "X-Export-Stats": f"rows={len(rows)}",
        },
    )


@router.get("/api/words/export.apkg")
async def export_words_anki(
    user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db),
):
    """
    Anki deck of every word the user is actively learning or already knows.
    Two-sided cards: front 汉字 + pinyin, back meaning + HSK level.
    No audio in this export — the per-word audio cache is shared with
    the existing vocab-list export; users who want audio per-word should
    use the vocab-list export path which prepares + caches first.
    """
    rows = (
        db.query(UserWord)
        .filter(UserWord.user_id == user.id, UserWord.state.in_(("learning", "known")))
        .order_by(UserWord.state.desc(), UserWord.word.asc())  # learning first
        .all()
    )

    model = genanki.Model(
        2147483600 + (hash(user.username) % 1000),
        "QingDu word state",
        fields=[
            {"name": "Hanzi"},
            {"name": "Pinyin"},
            {"name": "Meaning"},
            {"name": "HSKLevel"},
            {"name": "State"},
        ],
        templates=[
            {
                "name": "Recognition",
                "qfmt": ('<div style="font-size:72px; font-family: serif;">{{Hanzi}}</div>'),
                "afmt": (
                    '{{FrontSide}}<hr id="answer">'
                    '<div style="font-size:18px; color:#555;">{{Pinyin}}</div>'
                    '<div style="font-size:22px; margin-top:8px;">{{Meaning}}</div>'
                    '<div style="font-size:12px; margin-top:14px; '
                    'color:#888; font-family: monospace;">{{HSKLevel}} · {{State}}</div>'
                ),
            },
        ],
    )

    deck = genanki.Deck(
        2147483600 + (hash(f"{user.username}-words") % 1000),
        f"QingDu — {user.username}",
    )
    for r in rows:
        entry = hsk_vocab.get(r.word, {}) or {}
        note = genanki.Note(
            model=model,
            fields=[
                r.word,
                entry.get("pinyin", "") or "",
                entry.get("meaning", "") or "",
                entry.get("level", "") or "",
                r.state,
            ],
        )
        deck.add_note(note)

    fd, path = tempfile.mkstemp(suffix=".apkg", prefix="qingdu_words_")
    os.close(fd)
    try:
        genanki.Package(deck).write_to_file(path)
        with open(path, "rb") as f:
            data = f.read()
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="qingdu-words-{user.username}.apkg"',
            "X-Export-Stats": f"cards={len(rows)}",
        },
    )


# require_auth is referenced via require_auth_flexible's dependency tree, so
# the import is load-bearing — keep the name resolvable for static analysers.
_ = require_auth
