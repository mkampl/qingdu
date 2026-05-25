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
    """Walk every UserWord and rewrite pinyin + meaning if they've drifted
    from the current dictionary's view of the word. Returns the count
    of rows updated for logging."""
    updated = 0
    # Yield_per keeps memory flat for users who've accumulated thousands of rows.
    for row in db.query(UserWord).yield_per(500):
        fresh_pinyin, fresh_meaning = lookup_pinyin_meaning(row.word)
        # Only fields where the lookup found something better than the stored
        # snapshot get rewritten — preserves rows whose word isn't in any
        # dictionary at all (pypinyin fallback would otherwise wipe a
        # legitimate cached meaning from an earlier translation pass).
        changed = False
        if fresh_pinyin and fresh_pinyin != (row.pinyin or ""):
            row.pinyin = fresh_pinyin
            changed = True
        if fresh_meaning and fresh_meaning != (row.meaning or ""):
            row.meaning = fresh_meaning
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
