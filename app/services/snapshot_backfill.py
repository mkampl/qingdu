"""
Refresh the pinyin/meaning snapshots on every UserWord row so they
reflect the *current* dictionary (HSK + CC-CEDICT after every parser
or data-source change). Runs at app startup, after the dictionary
loaders complete, but only when the dictionary version
(`dict_data.dict_version()`) differs from the one stored after the last
run. A plain restart therefore touches no user rows at all.

Idempotent: we only write rows whose snapshot differs from what
`lookup_pinyin_meaning` produces today.
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

        # Keep legacy columns in sync with the dictionary gloss, unless the
        # headline came from a package: that snapshot is curated and must
        # survive dictionary changes like the package gloss row does.
        if row.meaning_source != "package":
            if fresh_meaning != (row.meaning or ""):
                row.meaning = fresh_meaning
                changed = True
            if fresh_pinyin and fresh_pinyin != (row.pinyin or ""):
                row.pinyin = fresh_pinyin
                changed = True

        if changed:
            updated += 1
    if updated:
        db.commit()
    return updated


def run_at_startup() -> int | None:
    """Helper called from `app.main.startup_event` so the call site
    doesn't have to manage its own session.

    Returns the number of rewritten rows, or None when the backfill was
    skipped (version unchanged, or dictionary data incomplete)."""
    from app.database import SessionLocal
    from app.services import dict_data

    current = dict_data.dict_version()
    if current is None:
        logger.warning("Dictionary data incomplete; skipping UserWord snapshot refresh")
        return None

    session = SessionLocal()
    try:
        stored = dict_data.get_stored_version(session)
        if stored == current:
            logger.info("Dictionary version %s unchanged; UserWord snapshots untouched", current)
            return None
        logger.info("Dictionary version %s -> %s; refreshing UserWord snapshots", stored, current)
        n = refresh_all_user_words(session)
        dict_data.set_stored_version(session, current)
        logger.info("Refreshed pinyin/meaning on %d UserWord rows", n)
        return n
    except Exception as e:  # noqa: BLE001
        logger.warning("UserWord snapshot refresh failed (%s) — skipping", e)
        session.rollback()
        return None
    finally:
        session.close()


__all__ = ["refresh_all_user_words", "run_at_startup"]
