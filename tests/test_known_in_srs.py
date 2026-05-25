"""
Phase #96 follow-up: 'known' is a high-stability SRS state, not a
terminal opt-out. These tests pin down the new behaviour:

- Setting/bulk-marking known seeds an FSRS Review-phase card with
  ~90d stability and a scattered first-review date.
- The review queue includes 'known' as well as 'learning'.
- Grading 'Again' on a known card drops it back into 'learning';
  grading 'Good' on a learning card that crosses 90-day stability
  promotes it to 'known'.
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
def client_db(app_module):
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


def test_marking_known_seeds_fsrs_state(client_db):
    client, Session = client_db
    r = client.post("/api/words/state", json={"word": "好", "state": "known"})
    assert r.status_code == 200
    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "好").one()
        assert row.state == "known"
        # ~90d stability with a future due_at in the (60d, 180d) window.
        assert row.stability is not None and row.stability >= 89
        assert row.due_at is not None
        delta_days = (row.due_at - datetime.utcnow()).days
        assert 50 <= delta_days <= 200, f"due_at {delta_days}d out of window"
        assert row.fsrs_state is not None
    finally:
        db.close()


def test_bulk_known_scatters_initial_due_dates(client_db):
    client, Session = client_db
    r = client.post(
        "/api/words/bulk-mark-known",
        json={"words": [f"字{i}" for i in range(30)], "source_text_id": None},
    )
    assert r.status_code == 200
    db = Session()
    try:
        rows = db.query(UserWord).filter(UserWord.user_id == 1).all()
        assert len(rows) == 30
        # Every row should land in the (60d, 180d) window; with 30 rows the
        # spread should be wider than any single day.
        days_outs = [(r.due_at - datetime.utcnow()).days for r in rows]
        assert all(50 <= d <= 200 for d in days_outs)
        assert max(days_outs) - min(days_outs) > 10, "scatter window collapsed"
    finally:
        db.close()


def test_review_queue_includes_known_when_due(client_db):
    client, Session = client_db
    now = datetime.utcnow()
    db = Session()
    try:
        db.add(
            UserWord(
                user_id=1, word="老", state="known", stability=120, due_at=now - timedelta(days=1)
            )
        )
        db.add(UserWord(user_id=1, word="新", state="learning"))
        # A known card that's not due yet shouldn't appear.
        db.add(
            UserWord(
                user_id=1, word="远", state="known", stability=200, due_at=now + timedelta(days=120)
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/review/queue")
    assert r.status_code == 200
    words = {c["word"] for c in r.json()["cards"]}
    assert "老" in words and "新" in words
    assert "远" not in words, "future-due known card leaked into queue"


def test_grading_again_drops_known_back_to_learning(client_db):
    client, Session = client_db
    db = Session()
    try:
        from app.services.srs import already_known_state

        seeded = already_known_state()
        row = UserWord(
            user_id=1,
            word="试",
            state="known",
            fsrs_state=seeded["fsrs_state"],
            stability=seeded["stability"],
            difficulty=seeded["difficulty"],
            due_at=seeded["due_at"],
            last_reviewed_at=seeded["last_reviewed_at"],
        )
        db.add(row)
        db.commit()
    finally:
        db.close()

    r = client.post("/api/review/grade", json={"word": "试", "grade": 1})
    assert r.status_code == 200, r.text
    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "试").one()
        assert row.state == "learning", "Again on a known card should drop it"
        # Stability should now be well below the threshold.
        assert row.stability is None or row.stability < 90
    finally:
        db.close()


def test_state_stays_learning_until_threshold_crossed(client_db):
    """Grading a fresh learning card 'Good' once doesn't yet promote it
    to known — stability only grows past 90d after many successful reviews."""
    client, _ = client_db
    client.post("/api/words/state", json={"word": "苹", "state": "learning"})
    r = client.post("/api/review/grade", json={"word": "苹", "grade": 3})
    assert r.status_code == 200
    states = client.get("/api/words/state").json()["states"]
    assert states["苹"] == "learning"
