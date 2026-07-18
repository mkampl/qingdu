"""Library reading-progress: mark-as-read and quiz grading.

Mirrors the review_client pattern in test_review.py — an in-memory SQLite
DB with dependency overrides for auth, so we exercise the real router/DB
wiring without touching the bundled library files on disk (those are
monkeypatched per-test via app.services.library).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user, require_auth
from app.database import Base, User, UserLibraryProgress, get_db
from app.services import library

QUIZ_ENTRY = {
    "slug": "hsk1_99_demo",
    "title": "demo",
    "hsk_level": 1,
    "topic": "demo",
    "char_count": 10,
    "text": "你好",
    "analyzed": {"words": []},
    "questions": [
        {"prompt": "What does 你好 mean?", "options": ["hello", "goodbye"], "answer_index": 0},
        {"prompt": "How many characters?", "options": ["1", "2", "3"], "answer_index": 1},
    ],
}

PLAIN_ENTRY = {**QUIZ_ENTRY, "slug": "hsk1_98_plain", "questions": []}


@pytest.fixture
def library_client(app_module, monkeypatch):
    entries = {QUIZ_ENTRY["slug"]: QUIZ_ENTRY, PLAIN_ENTRY["slug"]: PLAIN_ENTRY}
    monkeypatch.setattr(library, "get", lambda slug: entries.get(slug))
    monkeypatch.setattr(
        library, "questions", lambda slug: (entries.get(slug) or {}).get("questions") or None
    )
    monkeypatch.setattr(
        library,
        "quiz_questions",
        lambda slug: (
            [
                {"prompt": q["prompt"], "options": q["options"]}
                for q in ((entries.get(slug) or {}).get("questions") or [])
            ]
            or None
        ),
    )

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()
    db.add(User(id=1, username="alice", password_hash="x", must_change_password=False))
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


def test_mark_read_creates_progress_row(library_client):
    client, Session = library_client
    r = client.post(f"/api/library/{PLAIN_ENTRY['slug']}/read")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "read"

    progress = client.get("/api/library/progress").json()["items"]
    assert progress[PLAIN_ENTRY["slug"]]["status"] == "read"


def test_mark_read_unknown_slug_404s(library_client):
    client, _ = library_client
    r = client.post("/api/library/does-not-exist/read")
    assert r.status_code == 404


def test_unmark_read_clears_progress(library_client):
    client, _ = library_client
    client.post(f"/api/library/{PLAIN_ENTRY['slug']}/read")
    r = client.delete(f"/api/library/{PLAIN_ENTRY['slug']}/read")
    assert r.status_code == 200
    progress = client.get("/api/library/progress").json()["items"]
    assert PLAIN_ENTRY["slug"] not in progress


def test_quiz_endpoint_strips_answer_key(library_client):
    client, _ = library_client
    r = client.get(f"/api/library/{QUIZ_ENTRY['slug']}/quiz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["questions"]) == 2
    assert "answer_index" not in body["questions"][0]


def test_quiz_404s_when_text_has_no_questions(library_client):
    client, _ = library_client
    r = client.get(f"/api/library/{PLAIN_ENTRY['slug']}/quiz")
    assert r.status_code == 404


def test_all_correct_quiz_marks_progress_as_quiz(library_client):
    client, Session = library_client
    r = client.post(f"/api/library/{QUIZ_ENTRY['slug']}/quiz", json={"answers": [0, 1]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["all_correct"] is True
    assert body["results"] == [True, True]
    assert body["progress"]["status"] == "quiz"
    assert body["progress"]["score"] == 2

    db = Session()
    row = db.query(UserLibraryProgress).filter_by(user_id=1, slug=QUIZ_ENTRY["slug"]).first()
    assert row.status == "quiz"
    db.close()


def test_partially_correct_quiz_does_not_mark_progress(library_client):
    client, _ = library_client
    r = client.post(f"/api/library/{QUIZ_ENTRY['slug']}/quiz", json={"answers": [0, 0]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["all_correct"] is False
    assert body["results"] == [True, False]
    assert body["progress"] is None

    progress = client.get("/api/library/progress").json()["items"]
    assert QUIZ_ENTRY["slug"] not in progress


def test_quiz_pass_is_not_downgraded_by_a_later_manual_mark(library_client):
    """A manual 'mark as read' after a quiz pass should not weaken the
    recorded status back down to the self-reported tier."""
    client, _ = library_client
    client.post(f"/api/library/{QUIZ_ENTRY['slug']}/quiz", json={"answers": [0, 1]})
    client.post(f"/api/library/{QUIZ_ENTRY['slug']}/read")

    progress = client.get("/api/library/progress").json()["items"]
    assert progress[QUIZ_ENTRY["slug"]]["status"] == "quiz"


def test_quiz_wrong_answer_count_is_rejected(library_client):
    client, _ = library_client
    r = client.post(f"/api/library/{QUIZ_ENTRY['slug']}/quiz", json={"answers": [0]})
    assert r.status_code == 400
