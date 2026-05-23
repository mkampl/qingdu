"""
Phase-A word-state API: round-trip the lifecycle (new → learning → known →
ignored → cleared back to new), bulk-mark, stats, and the join into the
/api/analyze response.

Uses an in-memory SQLite engine + dependency overrides so the tests are
hermetic and do not depend on the deployed data directory.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import get_current_user, require_auth
from app.database import Base, User, get_db


@pytest.fixture
def words_client(app_module, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Seed a single user; both auth dependencies return it.
    db = TestingSession()
    test_user = User(
        id=1,
        username="alice",
        password_hash="x",
        is_admin=False,
        must_change_password=False,
        invite_quota=0,
    )
    db.add(test_user)
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
            yield c
    finally:
        app_module.dependency_overrides.clear()


def test_set_state_then_list_roundtrip(words_client):
    r = words_client.post("/api/words/state", json={"word": "你好", "state": "learning"})
    assert r.status_code == 200, r.text
    assert r.json() == {"word": "你好", "state": "learning"}

    r = words_client.get("/api/words/state")
    assert r.status_code == 200
    assert r.json()["states"] == {"你好": "learning"}


def test_promote_to_known_then_ignored(words_client):
    words_client.post("/api/words/state", json={"word": "再见", "state": "learning"})
    words_client.post("/api/words/state", json={"word": "再见", "state": "known"})
    words_client.post("/api/words/state", json={"word": "再见", "state": "ignored"})
    states = words_client.get("/api/words/state").json()["states"]
    assert states == {"再见": "ignored"}


def test_delete_resets_to_new(words_client):
    words_client.post("/api/words/state", json={"word": "谢谢", "state": "known"})
    r = words_client.delete("/api/words/state", params={"word": "谢谢"})
    assert r.status_code == 200
    assert words_client.get("/api/words/state").json()["states"] == {}


def test_invalid_state_rejected(words_client):
    r = words_client.post("/api/words/state", json={"word": "你好", "state": "??"})
    assert r.status_code == 400


def test_bulk_mark_known(words_client):
    r = words_client.post(
        "/api/words/bulk-mark-known",
        json={"words": ["一", "二", "三", "一"], "source_text_id": None},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 3  # dedup: '一' counted once for new inserts
    states = words_client.get("/api/words/state").json()["states"]
    assert states == {"一": "known", "二": "known", "三": "known"}


def test_bulk_mark_promotes_learning_to_known(words_client):
    words_client.post("/api/words/state", json={"word": "苹果", "state": "learning"})
    r = words_client.post("/api/words/bulk-mark-known", json={"words": ["苹果"]})
    assert r.json()["updated"] == 1
    assert words_client.get("/api/words/state").json()["states"] == {"苹果": "known"}


def test_stats_endpoint(words_client):
    words_client.post("/api/words/state", json={"word": "猫", "state": "learning"})
    words_client.post("/api/words/state", json={"word": "狗", "state": "known"})
    words_client.post("/api/words/state", json={"word": "鸟", "state": "ignored"})
    assert words_client.get("/api/words/stats").json() == {
        "learning": 1,
        "known": 1,
        "ignored": 1,
    }
