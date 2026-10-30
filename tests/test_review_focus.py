"""Review focus: which stage a card gets between intro and produce."""

from datetime import datetime, timedelta

import pytest

from app.database import UserWord
from app.services import srs


@pytest.mark.parametrize(
    ("focus", "stability", "learning_step", "stage"),
    [
        ("both", None, False, "intro"),
        ("both", 0.5, False, "intro"),
        ("both", 2.3, True, "trace"),  # the pass ~10 min after the intro
        ("both", 2.3, False, "read"),
        ("both", 9.9, False, "read"),
        ("both", 10.0, False, "produce"),
        ("both", 40.0, True, "trace"),  # relearning after a lapse
        ("reading", 2.3, True, "read"),
        ("reading", 40.0, False, "read"),
        ("writing", 2.3, False, "trace"),
        ("writing", 40.0, False, "produce"),
    ],
)
def test_stage_by_focus(focus, stability, learning_step, stage):
    assert srs.prompt_stage_for(stability, focus=focus, learning_step=learning_step) == stage


def test_learning_steps_follow_fsrs():
    first = srs.apply_grade(None, 3)
    assert srs.in_learning_steps(first["fsrs_state"])  # Good on a new card: +10 min
    second = srs.apply_grade(first["fsrs_state"], 3)
    assert not srs.in_learning_steps(second["fsrs_state"])
    assert not srs.in_learning_steps(None)


def test_new_word_is_written_again_then_read(review_client):
    client, _ = review_client
    # Intro pass graded Good: the word stays in the learning steps and
    # comes back in the session to be written from memory.
    r = client.post("/api/review/grade", json={"word": "一", "grade": 3, "mode": "writing"})
    assert r.json()["prompt_stage"] == "trace"
    # Written from memory: out of the learning steps, read next time.
    r = client.post("/api/review/grade", json={"word": "一", "grade": 3, "mode": "writing"})
    assert r.json()["prompt_stage"] == "read"


def test_focus_setting_round_trip_and_queue(review_client):
    client, Session = review_client
    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "二").one()
        row.stability = 30
        row.due_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    def stage():
        cards = client.get("/api/review/queue", params={"mode": "mixed"}).json()["cards"]
        return next(c for c in cards if c["word"] == "二")["prompt_stage"]

    assert stage() == "produce"  # both: write once established
    r = client.patch("/api/auth/me/settings", json={"review_focus": "reading"})
    assert r.status_code == 200, r.text
    assert r.json()["review_focus"] == "reading"
    assert stage() == "read"
    assert (
        client.patch("/api/auth/me/settings", json={"review_focus": "talking"}).status_code == 400
    )
