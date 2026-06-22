"""
SRS review router — queue ordering, grade roundtrip, stats endpoint.

We don't try to verify FSRS's math here (that's the upstream library's
job); we just verify our wiring: a graded card's due_at moves forward,
the queue stops returning it, and stats reflect the action.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user, require_auth
from app.database import Base, User, UserWord, get_db


@pytest.fixture
def review_client(app_module):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()
    db.add(
        User(
            id=1,
            username="alice",
            password_hash="x",
            is_admin=False,
            must_change_password=False,
            invite_quota=0,
        )
    )
    # Seed: two due cards (no due_at means brand-new in queue), one already
    # due in the past, one due far in the future (should NOT appear), one
    # ignored (should NOT appear). Known-with-due-in-the-past also appears
    # in the queue now that 'known' is just a high-stability SRS state.
    now = datetime.utcnow()
    db.add(UserWord(user_id=1, word="一", state="learning"))
    db.add(UserWord(user_id=1, word="二", state="learning", due_at=now - timedelta(hours=2)))
    db.add(UserWord(user_id=1, word="三", state="learning", due_at=now + timedelta(days=30)))
    db.add(UserWord(user_id=1, word="忽略", state="ignored"))
    db.add(
        UserWord(
            user_id=1,
            word="远期",
            state="known",
            stability=180,
            due_at=now + timedelta(days=120),
        )
    )
    db.commit()
    db.close()

    def _override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    def _override_user():
        s = TestingSession()
        try:
            return s.query(User).filter(User.id == 1).first()
        finally:
            s.close()

    app_module.dependency_overrides[get_db] = _override_get_db
    app_module.dependency_overrides[require_auth] = _override_user
    app_module.dependency_overrides[get_current_user] = _override_user
    try:
        with TestClient(app_module) as c:
            yield c, TestingSession
    finally:
        app_module.dependency_overrides.clear()


def test_queue_returns_only_due_active_cards(review_client):
    client, _ = review_client
    r = client.get("/api/review/queue")
    assert r.status_code == 200, r.text
    words = [c["word"] for c in r.json()["cards"]]
    assert "一" in words and "二" in words
    assert "三" not in words, "future-due card leaked into queue"
    assert "忽略" not in words, "ignored card leaked into queue"
    assert "远期" not in words, "future-due known card leaked into queue"


def test_queue_orders_nulls_first(review_client):
    client, _ = review_client
    r = client.get("/api/review/queue")
    words = [c["word"] for c in r.json()["cards"]]
    # 一 has due_at=NULL, 二 has due_at in the past — NULLs come first so
    # never-reviewed-but-learning words get attention before old laggards.
    assert words.index("一") < words.index("二")


def test_grade_updates_due_at_and_removes_from_queue(review_client):
    """Single-mode (cycle=False) — every grade advances FSRS immediately.
    This is the pre-Phase-1.3 behaviour, surfaced through the Advanced
    toggle in the UI."""
    client, Session = review_client
    r = client.post(
        "/api/review/grade",
        json={"word": "一", "grade": 3, "cycle": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["word"] == "一"
    assert body["due_at"] is not None
    assert body["stability"] is not None and body["stability"] > 0
    assert body["fsrs_advanced"] is True

    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "一").one()
        assert row.due_at is not None
        assert row.due_at > datetime.utcnow() - timedelta(seconds=1)
        assert row.fsrs_state is not None
    finally:
        db.close()


def test_grade_creates_row_for_unknown_word(review_client):
    """Even in mixed mode, an unknown-word grade still creates the row.
    Cycle gating means FSRS doesn't advance on a single passing grade,
    but the row exists with the modality logged."""
    client, Session = review_client
    r = client.post(
        "/api/review/grade",
        json={"word": "新词", "grade": 4, "mode": "recognition"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Mixed-mode default: passing the first modality doesn't advance FSRS.
    assert body["fsrs_advanced"] is False
    assert body["cycle_modes_completed"] == ["recognition"]
    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "新词").one()
        assert row.state == "learning"
        # due_at stays NULL — FSRS hasn't run yet.
        assert row.due_at is None
        # The cycle has one mode banked.
        assert row.modes_completed == '["recognition"]'
    finally:
        db.close()


def test_mixed_cycle_advances_fsrs_after_all_four_modes(review_client):
    """Phase 1.3 — all four modalities at Good or better completes the
    cycle, which is when FSRS finally advances and the cycle resets."""
    client, Session = review_client
    for i, mode in enumerate(["recognition", "cloze", "dictation", "writing"]):
        r = client.post(
            "/api/review/grade",
            json={"word": "一", "grade": 3, "mode": mode},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if i < 3:
            assert body["fsrs_advanced"] is False, mode
            assert body["cycle_complete"] is False
            assert mode in body["cycle_modes_completed"]
        else:
            # Fourth modality completes the cycle.
            assert body["fsrs_advanced"] is True
            assert body["cycle_complete"] is True
            assert body["cycle_modes_completed"] == []
            assert body["due_at"] is not None

    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "一").one()
        # Cycle cleared on completion so the next card start is fresh.
        assert row.modes_completed == "[]"
        assert row.modes_cycle_started_at is None
    finally:
        db.close()


def test_mixed_cycle_failing_grade_resets_cycle_and_advances_fsrs(review_client):
    """A Hard / Again grade in mixed mode wipes the cycle (the user has
    to start over) AND advances FSRS — the scheduler needs the negative
    signal even though the cycle didn't complete."""
    client, Session = review_client
    # Pass recognition first.
    client.post(
        "/api/review/grade",
        json={"word": "一", "grade": 3, "mode": "recognition"},
    )
    # Then fail dictation.
    r = client.post(
        "/api/review/grade",
        json={"word": "一", "grade": 1, "mode": "dictation"},
    )
    body = r.json()
    assert body["fsrs_advanced"] is True
    assert body["cycle_complete"] is False
    assert body["cycle_modes_completed"] == []

    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "一").one()
        assert row.modes_completed == "[]"
        # FSRS ran with grade=1 so due_at is set (back to soon).
        assert row.due_at is not None
    finally:
        db.close()


def test_invalid_grade_rejected(review_client):
    client, _ = review_client
    r = client.post("/api/review/grade", json={"word": "一", "grade": 7})
    assert r.status_code == 400


def test_stats_endpoint(review_client):
    client, _ = review_client
    r = client.get("/api/review/stats")
    assert r.status_code == 200
    body = r.json()
    # learning counter is just state='learning' rows ('一', '二', '三').
    assert body["learning"] == 3
    # 2 are due now ('一' null + '二' past); '三' is future-due, the known
    # row is future-due, the ignored row never appears.
    assert body["due_now"] == 2
    # No reviews yet -> 0.
    assert body["reviewed_today"] == 0

    # Grade one (single-mode so FSRS advances and the card moves out of
    # 'due now' immediately — mixed-mode would need four grades).
    client.post(
        "/api/review/grade",
        json={"word": "一", "grade": 3, "cycle": False},
    )
    body2 = client.get("/api/review/stats").json()
    assert body2["reviewed_today"] == 1
    assert body2["due_now"] == 1  # '一' moved out of the due window
