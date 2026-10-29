"""
Personal-data exports: a CSV of all your word states and an Anki deck of
the words you are learning or know. Both use require_auth_flexible so
plain download links work without an Authorization header.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import logging
import os
import tempfile

import genanki
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import require_auth_flexible
from app.database import User, UserWord, get_db
from app.services.timestamps import iso_utc
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


def _stable_id(key: str) -> int:
    """Anki model or deck id for `key`, the same on every run, so a second
    import updates the deck instead of adding another one (Python's hash()
    is salted per process)."""
    return 2147483600 + int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big") % 1000


@router.get("/api/words/export.csv")
async def export_words_csv(
    user: User = Depends(require_auth_flexible),
    db: Session = Depends(get_db),
):
    """All of the user's word states as CSV."""
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
                "due_at": iso_utc(r.due_at) or "",
                "last_reviewed_at": iso_utc(r.last_reviewed_at) or "",
                "created_at": iso_utc(r.created_at) or "",
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
    """Anki deck of every word the user is learning or knows: front 汉字,
    back pinyin, meaning and HSK level. No audio; the vocab-list export
    has it."""
    rows = (
        db.query(UserWord)
        .filter(UserWord.user_id == user.id, UserWord.state.in_(("learning", "known")))
        .order_by(UserWord.state.desc(), UserWord.word.asc())  # learning first
        .all()
    )

    model = genanki.Model(
        _stable_id(user.username),
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
        _stable_id(f"{user.username}-words"),
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
