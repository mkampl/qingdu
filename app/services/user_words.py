"""Writes to a user's word states: UserWord rows, their glosses and the
UserWordEvent log the activity stats read.

- Absence of a UserWord row == 'new' (never touched).
- A row's `state` column is one of {'learning', 'known', 'ignored'}.
- Every mutation also appends a UserWordEvent.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.database import SavedText, User, UserWord, UserWordEvent, UserWordGloss
from app.services import library, srs
from app.services.levels import level_number
from app.services.lexicon import is_lexical_word, user_word_sources
from app.services.script import to_canonical
from app.services.srs import ALREADY_KNOWN_STABILITY_DAYS, already_known_state
from app.services.streak import record_activity
from app.services.word_info import lookup_pinyin_meaning
from app.state import hsk_vocab


def record_event(
    db: Session,
    user_id: int,
    word: str,
    event_type: str,
    new_state: str | None = None,
    source_text_id: int | None = None,
) -> None:
    db.add(
        UserWordEvent(
            user_id=user_id,
            word=word,
            event_type=event_type,
            new_state=new_state,
            source_text_id=source_text_id,
        )
    )


def apply_known_scheduling(row: UserWord) -> None:
    """Schedule a row as "already known" — Review-phase FSRS card with
    ~90d stability and a randomised first-review date in (60d, 180d).
    State stays 'known' so the reader colours it accordingly; known cards
    stay in the review rotation."""
    seeded = already_known_state()
    row.state = "known"
    row.fsrs_state = seeded["fsrs_state"]
    row.stability = seeded["stability"]
    row.difficulty = seeded["difficulty"]
    row.due_at = seeded["due_at"]
    row.last_reviewed_at = seeded["last_reviewed_at"]


def ensure_gloss(
    db: Session,
    row: UserWord,
    *,
    pinyin: str | None,
    meaning: str | None,
    source: str,
    source_tag: str | None,
) -> None:
    """Add a gloss to a UserWord row unless one with the same (source,
    source_tag) exists. The row's own `meaning`/`pinyin` snapshot takes
    the first gloss it gets.
    """
    if not meaning:
        return
    existing = next(
        (
            g
            for g in row.glosses
            if g.source == source and (g.source_tag or None) == (source_tag or None)
        ),
        None,
    )
    if existing is not None:
        # A dictionary gloss follows the current dictionary (e.g. a better
        # CC-CEDICT primary). Other glosses are kept as they are.
        if source == "dictionary":
            if meaning and meaning != existing.meaning:
                existing.meaning = meaning
            if pinyin and pinyin != existing.pinyin:
                existing.pinyin = pinyin
        return
    db.add(
        UserWordGloss(
            user_word=row,
            pinyin=pinyin or None,
            meaning=meaning,
            source=source,
            source_tag=source_tag,
        )
    )
    if not row.meaning:
        row.meaning = meaning
        row.pinyin = pinyin or None
        row.meaning_source = source


def may_create_word(db: Session, user_id: int, word: str, *, is_pkg: bool = False) -> bool:
    """Whether a new UserWord row may be created for `word`. Dictionary
    words, the user's own list and package words, and words clicked in a
    package text qualify; phrases such as 很多 or 洗衣服 do not. An
    existing row can always be updated, so this only guards inserts."""
    if is_pkg:
        return True
    exists = (
        db.query(UserWord.id).filter(UserWord.user_id == user_id, UserWord.word == word).first()
    )
    return exists is not None or is_lexical_word(word, db=db, user_id=user_id)


def seed_glosses(
    db: Session,
    row: UserWord,
    word: str,
    is_pkg: bool,
    pkg_pinyin: str | None,
    pkg_meaning: str | None,
    pkg_tag: str | None,
) -> None:
    """Always a dictionary gloss (the default learner-facing meaning,
    whatever context the word was met in), plus a package gloss tagged by
    package name when the word came from one."""
    dict_pinyin, dict_meaning = lookup_pinyin_meaning(word)
    if dict_meaning:
        ensure_gloss(
            db,
            row,
            pinyin=dict_pinyin,
            meaning=dict_meaning,
            source="dictionary",
            source_tag=None,
        )
    if is_pkg:
        ensure_gloss(
            db,
            row,
            pinyin=pkg_pinyin,
            meaning=pkg_meaning,
            source="package",
            source_tag=pkg_tag or "package",
        )


def upsert_word(
    db: Session,
    user_id: int,
    word: str,
    state: str,
    source_text_id: int | None,
    pkg_meaning: str | None = None,
    pkg_pinyin: str | None = None,
    pkg_translation_source: str | None = None,
    pkg_source_tag: str | None = None,
) -> UserWord:
    is_pkg = pkg_translation_source == "package" and (pkg_meaning or pkg_pinyin) is not None

    row = db.query(UserWord).filter(UserWord.user_id == user_id, UserWord.word == word).first()
    if row is None:
        row = UserWord(
            user_id=user_id,
            word=word,
            state=state,
            seen_count=1,
        )
        if state == "known":
            apply_known_scheduling(row)
        db.add(row)
        db.flush()  # row.id needed for gloss FK
    else:
        # Same guard as mark_known: a mature card (stability already
        # past the "known" seed) keeps its FSRS history instead of being
        # reseeded to 90 days.
        if state == "known" and (row.stability or 0) < ALREADY_KNOWN_STABILITY_DAYS:
            apply_known_scheduling(row)
        else:
            row.state = state
        row.seen_count = (row.seen_count or 0) + 1
        row.updated_at = datetime.utcnow()

    seed_glosses(db, row, word, is_pkg, pkg_pinyin, pkg_meaning, pkg_source_tag)
    record_event(db, user_id, word, "state_change", state, source_text_id)
    return row


def context_title(
    db: Session, user_id: int, source_text_id: int | None, library_slug: str | None
) -> str | None:
    """Title of the text a word was marked in: one of the user's saved
    texts, else a bundled library text."""
    if source_text_id is not None:
        title = (
            db.query(SavedText.title)
            .filter(SavedText.id == source_text_id, SavedText.user_id == user_id)
            .scalar()
        )
        if title:
            return title
    if library_slug:
        entry = library.get(library_slug)
        if entry:
            return entry.get("title")
    return None


def user_glosses_map(db: Session, user: User | None) -> dict[str, list[dict]]:
    """For each word the user has touched, the glosses they've collected
    with provenance. The popover shows them, so a Daoist 道 shows both the
    dictionary primary and the Daodejing package gloss. One indexed join."""
    if user is None:
        return {}
    rows = (
        db.query(
            UserWord.word,
            UserWordGloss.source,
            UserWordGloss.source_tag,
            UserWordGloss.meaning,
            UserWordGloss.pinyin,
        )
        .join(UserWordGloss, UserWordGloss.user_word_id == UserWord.id)
        .filter(UserWord.user_id == user.id)
        .order_by(UserWord.word, UserWordGloss.created_at)
        .all()
    )
    out: dict[str, list[dict]] = {}
    for word, source, tag, meaning, pinyin in rows:
        out.setdefault(word, []).append(
            {"source": source, "tag": tag, "meaning": meaning, "pinyin": pinyin}
        )
    return out


def mark_known(
    db: Session,
    user: User,
    words_in: list[str],
    snapshots: dict | None,
    source_text_id: int | None,
) -> dict:
    """Promote a batch of words to 'known' (see POST /api/words/bulk-mark-known)."""
    # Dedup at the boundary — callers may include the same word twice (e.g.
    # multiple sentences in the same section). Without this we'd try to
    # insert the same (user_id, word) row twice and trip the unique index.
    seen: set[str] = set()
    words: list[str] = []
    for w in words_in:
        if not w:
            continue
        stripped = to_canonical(w.strip(), user)
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        words.append(stripped)
    if not words:
        return {"updated": 0, "total": 0, "skipped": []}

    existing = {
        r.word: r
        for r in db.query(UserWord)
        .filter(UserWord.user_id == user.id, UserWord.word.in_(words))
        .all()
    }
    # Resolve a per-word package snapshot, if one was supplied. The
    # mapping is keyed by canonical surface form so it survives the
    # to_canonical() pass above.
    snapshots = snapshots or {}
    updated = 0
    skipped: list[str] = []
    own_words: set[str] | None = None
    for word in words:
        snap = snapshots.get(word)
        pkg_meaning = snap.meaning if snap else None
        pkg_pinyin = snap.pinyin if snap else None
        pkg_source = snap.translation_source if snap else None
        pkg_tag = snap.package_source if snap else None
        is_pkg = pkg_source == "package" and (pkg_meaning or pkg_pinyin) is not None

        row = existing.get(word)
        if row is None and not is_pkg and not is_lexical_word(word):
            if own_words is None:
                own_words = user_word_sources(db, user.id)
            if word not in own_words:
                skipped.append(word)
                continue
        if row is None:
            row = UserWord(user_id=user.id, word=word, state="learning", seen_count=1)
            apply_known_scheduling(row)
            db.add(row)
            db.flush()
            updated += 1
        elif (row.stability or 0) < ALREADY_KNOWN_STABILITY_DAYS:
            apply_known_scheduling(row)
            row.updated_at = datetime.utcnow()
            updated += 1

        seed_glosses(db, row, word, is_pkg, pkg_pinyin, pkg_meaning, pkg_tag)
        record_event(db, user.id, word, "bulk_mark_known", "known", source_text_id)
    record_activity(user, db)
    db.commit()
    return {"updated": updated, "total": len(words), "skipped": skipped}


def _hsk_words_at_or_below(up_to_level: int, hsk_version: str) -> list[str]:
    """
    Return the list of HSK words at level <= `up_to_level` for the chosen
    version. Single-character entries are included; that's intentional —
    they're how learners build pinyin / radical recognition even before
    they read the compounds.
    """
    field = "level_new" if hsk_version == "new" else "level_old"
    prefix = "new-" if hsk_version == "new" else "old-"
    return [
        word
        for word, entry in hsk_vocab.items()
        if (n := level_number(entry.get(field), (prefix,))) is not None and n <= up_to_level
    ]


def import_hsk_known(db: Session, user: User, up_to_level: int, hsk_version: str) -> dict:
    """Mark every HSK word at level <= up_to_level as known. Words the user
    has already touched are left alone (an 'ignored' or 'learning' word is
    not overwritten; this only fills the void)."""
    candidates = _hsk_words_at_or_below(up_to_level, hsk_version)
    if not candidates:
        return {"inserted": 0, "skipped": 0, "total_eligible": 0}

    # Find which candidates the user has already touched.
    existing_rows = (
        db.query(UserWord.word)
        .filter(UserWord.user_id == user.id, UserWord.word.in_(candidates))
        .all()
    )
    existing = {w for (w,) in existing_rows}

    to_insert = [w for w in candidates if w not in existing]
    for word in to_insert:
        pinyin, meaning = lookup_pinyin_meaning(word)
        row = UserWord(
            user_id=user.id,
            word=word,
            state="learning",
            seen_count=1,
            pinyin=pinyin or None,
            meaning=meaning or None,
            meaning_source="dictionary",
        )
        apply_known_scheduling(row)
        db.add(row)
    # Single event row marking the bulk action — avoids 2 000+ event rows
    # for the typical "mark HSK 1–4" use.
    db.add(
        UserWordEvent(
            user_id=user.id,
            word=f"hsk-{hsk_version}-<=L{up_to_level}",
            event_type="bulk_mark_known",
            new_state="known",
            word_count=len(to_insert),
        )
    )
    record_activity(user, db)
    db.commit()
    return {
        "inserted": len(to_insert),
        "skipped": len(existing),
        "total_eligible": len(candidates),
    }


# grade_word moves review rows between 'learning' and 'known' based on the
# FSRS stability after grading.
KNOWN_STABILITY_THRESHOLD_DAYS = 90.0


def next_state_after_grade(state: str, stability: float | None, grade: int) -> str:
    """Learning/known transition after one grade (hysteresis).

    learning → known once stability reaches KNOWN_STABILITY_THRESHOLD_DAYS.
    known → learning only on Again; Hard/Good/Easy keep a known card known.
    """
    if state == "known":
        return "learning" if grade == 1 else "known"
    if (stability or 0) >= KNOWN_STABILITY_THRESHOLD_DAYS:
        return "known"
    return "learning"


def grade_word(db: Session, row: UserWord, grade: int, mode: str, retention: float | None) -> None:
    """One FSRS step for a graded review card, its learning/known transition
    and the review events."""
    updated = srs.apply_grade(row.fsrs_state, grade, retention=retention)
    row.fsrs_state = updated["fsrs_state"]
    row.stability = updated["stability"]
    row.difficulty = updated["difficulty"]
    row.due_at = updated["due_at"]
    row.last_reviewed_at = updated["last_reviewed_at"]
    row.updated_at = datetime.utcnow()

    # Auto-transition between 'learning' and 'known' based on the new
    # FSRS stability. Crossing into 'known' = mastered (renders as
    # known-color in the reader). The way back is deliberately narrower:
    # only a lapse (Again) demotes a known card. FSRS's same-day formula
    # can drop stability far below the threshold on a plain Hard (90 →
    # ~41), and that is not the user saying "I forgot this word".
    # State flips are emitted as state_change events so the log captures
    # the inflection (helps with stats + undo).
    new_state_for_row = next_state_after_grade(row.state, row.stability, grade)
    if new_state_for_row != row.state:
        row.state = new_state_for_row
        db.add(
            UserWordEvent(
                user_id=row.user_id,
                word=row.word,
                event_type="state_change",
                new_state=new_state_for_row,
            )
        )

    db.add(
        UserWordEvent(
            user_id=row.user_id,
            word=row.word,
            event_type="review",
            new_state=row.state,
            grade=grade,
            mode=mode,
        )
    )
