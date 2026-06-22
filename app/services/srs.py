"""
FSRS-4.5 wrapper around the `fsrs` package. Keeps every direct call to
`fsrs` in this one module so the rest of the codebase doesn't depend on
the third-party API surface — if we ever swap algorithms (back to SM-2,
forward to FSRS-5/6, custom), only this file changes.

Storage shape (per UserWord row):
- `fsrs_state` (TEXT JSON) — full Card round-trip; source of truth.
- `stability` / `difficulty` (FLOAT) — mirrored from the Card for analytics.
- `due_at` (DATETIME) — mirrored for indexed "due now" queries.
- `last_reviewed_at` (DATETIME) — mirrored for stats + UI.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from fsrs import Card, Rating, Scheduler, State

# Default scheduler — 0.95 retention target. Closer to classic Anki SM-2
# intuition than the FSRS-library default of 0.90 (which gives jarring
# 10-day intervals after only three "Good"s). Users can override the
# retention per-account via Settings → Review challenge; we build a
# fresh Scheduler in that case.
DEFAULT_RETENTION = 0.95
_scheduler = Scheduler(desired_retention=DEFAULT_RETENTION)


def _scheduler_for(retention: float | None) -> Scheduler:
    if retention is None or abs(retention - DEFAULT_RETENTION) < 1e-9:
        return _scheduler
    # Clamp to the meaningful tuning band even if the caller wandered out.
    r = max(0.85, min(0.97, float(retention)))
    return Scheduler(desired_retention=r)


VALID_GRADES = (1, 2, 3, 4)


def _to_rating(grade: int) -> Rating:
    if grade not in VALID_GRADES:
        raise ValueError(f"grade must be one of {VALID_GRADES}, got {grade}")
    # The Rating enum's integer values line up 1:1 with our grade ints.
    return Rating(grade)


def card_from_state(state_json: str | None) -> Card:
    """
    Reconstruct an FSRS Card from the JSON we stored. Returns a fresh Card
    when state_json is None / empty — that's how we onboard a word that
    was 'learning' before Phase B shipped (or any word with no review history).
    """
    if not state_json:
        return Card()
    return Card.from_json(state_json)


def apply_grade(state_json: str | None, grade: int, retention: float | None = None) -> dict:
    """
    Run one review step. Returns a dict ready to splat into a UserWord:

        {
            "fsrs_state": "<json>",
            "stability": float,
            "difficulty": float,
            "due_at": datetime (naive UTC, to match the rest of the schema),
            "last_reviewed_at": datetime (naive UTC),
        }

    `retention` overrides the default 0.95 desired_retention. Pass the
    caller's user.review_retention so per-user tuning takes effect from
    the very next grade (existing cards just get their next due_at
    recomputed with the new scheduler).
    """
    card = card_from_state(state_json)
    rating = _to_rating(grade)
    scheduler = _scheduler_for(retention)
    new_card, _log = scheduler.review_card(card, rating)
    return {
        "fsrs_state": new_card.to_json(),
        "stability": new_card.stability,
        "difficulty": new_card.difficulty,
        # FSRS uses tz-aware UTC; our DateTime columns are naive (legacy choice
        # from the rest of the schema). Strip the tz so we don't mix and match.
        "due_at": _as_naive_utc(new_card.due),
        "last_reviewed_at": _as_naive_utc(new_card.last_review)
        if new_card.last_review
        else datetime.utcnow(),
    }


def initial_state() -> dict:
    """
    Returns the same dict shape as apply_grade for a brand-new card — used
    when we want to seed FSRS state for a word that's been promoted to
    'learning' but never explicitly reviewed yet (so it shows up in the
    queue with due=now).
    """
    card = Card()
    return {
        "fsrs_state": card.to_json(),
        "stability": card.stability,
        "difficulty": card.difficulty,
        "due_at": _as_naive_utc(card.due),
        "last_reviewed_at": None,
    }


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalize a tz-aware datetime to naive UTC."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


# Window over which "I already know this" cards' first reviews scatter.
# Bulk imports (HSK 1–4 = ~3400 cards) would otherwise all come due on the
# same day; spreading them across (60d, 180d) keeps ~30 cards/day at peak.
ALREADY_KNOWN_MIN_DAYS = 60
ALREADY_KNOWN_MAX_DAYS = 180
ALREADY_KNOWN_STABILITY_DAYS = 90.0
ALREADY_KNOWN_DIFFICULTY = 4.0  # "Easy"-end of the 1–10 FSRS difficulty band


def already_known_state(jitter_seed: int | None = None) -> dict:
    """
    Seed an FSRS Card in the Review phase with ~90d stability so the card
    behaves like one the user has graded `Easy` a handful of times. The
    first review fires at a random point in the 60–180-day window so
    bulk-knowing 3000+ words doesn't pile every review on day 90.

    Returns the same shape `apply_grade`/`initial_state` use so callers
    can splat it into a UserWord row directly.
    """
    rng = random.Random(jitter_seed) if jitter_seed is not None else random
    days_until_due = rng.uniform(ALREADY_KNOWN_MIN_DAYS, ALREADY_KNOWN_MAX_DAYS)
    now_utc = datetime.now(UTC)
    due = now_utc + timedelta(days=days_until_due)
    card = Card(
        state=State.Review,
        stability=ALREADY_KNOWN_STABILITY_DAYS,
        difficulty=ALREADY_KNOWN_DIFFICULTY,
        due=due,
        last_review=now_utc,
    )
    return {
        "fsrs_state": card.to_json(),
        "stability": card.stability,
        "difficulty": card.difficulty,
        "due_at": _as_naive_utc(card.due),
        "last_reviewed_at": _as_naive_utc(now_utc),
    }


# --- Phase 1.3: mixed-mode cycle gating ------------------------------------
#
# When the user reviews a card in Mixed mode, FSRS only advances after
# every modality has been graded Good (3) or Easy (4). A Hard (2) or
# Again (1) on any modality resets the cycle so the next attempt starts
# from Recognition. The four modes are the same as ReviewMode in
# app/routers/review.py.

ALL_REVIEW_MODES = ("recognition", "cloze", "dictation", "writing")
PASSING_GRADE = 3  # Good or Easy advances the cycle; Hard / Again resets.


def should_advance_fsrs(modes_completed: list[str], mode: str, grade: int) -> bool:
    """Decide whether this grade should call apply_grade and advance the FSRS
    scheduler in Mixed mode.

    Returns True only when:
    1. The grade is Good or Easy (a Hard / Again always defers FSRS to the
       next attempt and the caller should reset `modes_completed`), and
    2. With `mode` added to `modes_completed`, every modality in
       ALL_REVIEW_MODES is covered.

    Single-mode reviews (Advanced toggle) bypass this helper and call
    apply_grade directly — they're equivalent to today's behaviour.
    """
    if grade < PASSING_GRADE:
        return False
    covered = set(modes_completed) | {mode}
    return all(m in covered for m in ALL_REVIEW_MODES)


def next_cycle_mode(modes_completed: list[str]) -> str | None:
    """Pick the next modality to test in a Mixed-mode cycle, in canonical
    Recognition → Cloze → Dictation → Writing order. Returns None when
    the cycle is already complete."""
    for m in ALL_REVIEW_MODES:
        if m not in modes_completed:
            return m
    return None


__all__ = [
    "ALL_REVIEW_MODES",
    "ALREADY_KNOWN_STABILITY_DAYS",
    "PASSING_GRADE",
    "VALID_GRADES",
    "already_known_state",
    "apply_grade",
    "card_from_state",
    "initial_state",
    "next_cycle_mode",
    "should_advance_fsrs",
]
