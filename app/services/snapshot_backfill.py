"""
Refresh the pinyin/meaning snapshots on every UserWord row so they
reflect the *current* dictionary (HSK + CC-CEDICT after every parser
or data-source change). Runs once at app startup, after the dictionary
loaders complete.

Idempotent: we only write rows whose snapshot differs from what
`lookup_pinyin_meaning` produces today, so a no-op restart costs one
read per row and zero writes.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.database import UserWord
from app.services.word_info import lookup_pinyin_meaning

logger = logging.getLogger(__name__)


def refresh_all_user_words(db: Session) -> int:
    """Walk every UserWord and refresh its dictionary-sourced gloss from
    the current view of HSK + CC-CEDICT. Package-sourced glosses are
    immutable (the user clicked them in a specific package context, the
    package's curated meaning is the source of truth).

    Also keeps the legacy UserWord.meaning / .pinyin columns in sync
    with the first gloss so older read paths still work."""
    from app.database import UserWordGloss

    updated = 0
    for row in db.query(UserWord).yield_per(500):
        fresh_pinyin, fresh_meaning = lookup_pinyin_meaning(row.word)
        if not fresh_meaning:
            continue
        # Find the dictionary gloss for this row, if any.
        dict_gloss = next(
            (g for g in row.glosses if g.source == "dictionary"),
            None,
        )
        changed = False
        if dict_gloss is None:
            # Row has no dictionary gloss yet — create one. Happens for
            # rows that were originally package-only and the user has
            # now run a backfill against a richer dictionary.
            db.add(
                UserWordGloss(
                    user_word=row,
                    pinyin=fresh_pinyin or None,
                    meaning=fresh_meaning,
                    source="dictionary",
                    source_tag=None,
                )
            )
            changed = True
        else:
            if fresh_meaning and fresh_meaning != dict_gloss.meaning:
                dict_gloss.meaning = fresh_meaning
                changed = True
            if fresh_pinyin and fresh_pinyin != (dict_gloss.pinyin or ""):
                dict_gloss.pinyin = fresh_pinyin
                changed = True

        # Keep legacy columns in sync. Order: the dictionary gloss is
        # the canonical default headline; if there's only a package
        # gloss, use that.
        primary_meaning = fresh_meaning
        primary_pinyin = fresh_pinyin
        if primary_meaning and primary_meaning != (row.meaning or ""):
            row.meaning = primary_meaning
            changed = True
        if primary_pinyin and primary_pinyin != (row.pinyin or ""):
            row.pinyin = primary_pinyin
            changed = True

        if changed:
            updated += 1
    if updated:
        db.commit()
    return updated


def run_at_startup() -> None:
    """Helper called from `app.main.startup_event` so the call site
    doesn't have to manage its own session."""
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        n = refresh_all_user_words(session)
        if n:
            logger.info("Refreshed pinyin/meaning on %d UserWord rows", n)
    except Exception as e:  # noqa: BLE001
        logger.warning("UserWord snapshot refresh failed (%s) — skipping", e)
        session.rollback()
    finally:
        session.close()


__all__ = ["refresh_all_user_words", "run_at_startup"]
