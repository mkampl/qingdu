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

from datetime import UTC, datetime

from fsrs import Card, Rating, Scheduler

# One module-level scheduler is fine — Scheduler() is just a parameter bag.
# Default desired_retention is 0.9, which matches the Anki community baseline.
_scheduler = Scheduler()


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


def apply_grade(state_json: str | None, grade: int) -> dict:
    """
    Run one review step. Returns a dict ready to splat into a UserWord:

        {
            "fsrs_state": "<json>",
            "stability": float,
            "difficulty": float,
            "due_at": datetime (naive UTC, to match the rest of the schema),
            "last_reviewed_at": datetime (naive UTC),
        }
    """
    card = card_from_state(state_json)
    rating = _to_rating(grade)
    new_card, _log = _scheduler.review_card(card, rating)
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


__all__ = ["VALID_GRADES", "apply_grade", "card_from_state", "initial_state"]
