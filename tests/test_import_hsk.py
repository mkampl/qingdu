"""
POST /api/words/import-hsk — bulk-mark HSK levels as known. We seed a
small in-memory HSK vocab so the test doesn't depend on the GitHub
download path or on real-world counts.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import state as _state
from app.auth import get_current_user, require_auth
from app.database import Base, User, UserWord, get_db

# A few canonical HSK entries spanning levels.
_SAMPLE_VOCAB = {
    "你": {"level_new": "new-1"},
    "好": {"level_new": "new-1"},
    "今天": {"level_new": "new-1"},
    "学习": {"level_new": "new-2"},
    "汉字": {"level_new": "new-3"},
    "复杂": {"level_new": "new-4"},
    "高级": {"level_new": "new-5"},
    "繁": {"level_old": "old-3"},
    "體": {"level_old": "old-4"},
}


@pytest.fixture
def import_client(app_module):
    """Stand up an isolated DB + auth + seeded HSK vocab for these tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()
    db.add(User(id=1, username="alice", password_hash="x", invite_quota=0))
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
        # TestClient's __enter__ runs the FastAPI startup event, which
        # repopulates hsk_vocab from the loader. We swap our seeded vocab
        # in AFTER startup so the route handlers see our small fixture.
        with TestClient(app_module) as c:
            saved = dict(_state.hsk_vocab)
            _state.hsk_vocab.clear()
            _state.hsk_vocab.update(_SAMPLE_VOCAB)
            try:
                yield c, TestingSession
            finally:
                _state.hsk_vocab.clear()
                _state.hsk_vocab.update(saved)
    finally:
        app_module.dependency_overrides.clear()


def test_import_hsk_level_2_includes_levels_1_and_2(import_client):
    client, _ = import_client
    r = client.post("/api/words/import-hsk", json={"up_to_level": 2, "hsk_version": "new"})
    assert r.status_code == 200, r.text
    body = r.json()
    # 3 HSK 1 + 1 HSK 2 = 4 eligible from the seeded vocab.
    assert body["total_eligible"] == 4
    assert body["inserted"] == 4
    assert body["skipped"] == 0


def test_import_hsk_is_idempotent(import_client):
    client, _ = import_client
    client.post("/api/words/import-hsk", json={"up_to_level": 1, "hsk_version": "new"})
    r = client.post("/api/words/import-hsk", json={"up_to_level": 1, "hsk_version": "new"})
    body = r.json()
    assert body["inserted"] == 0
    assert body["skipped"] == 3  # already known


def test_import_old_hsk_uses_level_old_field(import_client):
    client, _ = import_client
    r = client.post("/api/words/import-hsk", json={"up_to_level": 3, "hsk_version": "old"})
    body = r.json()
    # 繁 is old-3 → in. 體 is old-4 → out.
    assert body["total_eligible"] == 1
    assert body["inserted"] == 1


def test_invalid_level_rejected(import_client):
    client, _ = import_client
    assert (
        client.post(
            "/api/words/import-hsk", json={"up_to_level": 99, "hsk_version": "new"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/words/import-hsk", json={"up_to_level": 1, "hsk_version": "??"}
        ).status_code
        == 400
    )


def test_words_land_as_known_state(import_client):
    client, Session = import_client
    client.post("/api/words/import-hsk", json={"up_to_level": 1, "hsk_version": "new"})
    db = Session()
    try:
        rows = db.query(UserWord).filter(UserWord.user_id == 1).all()
        assert {r.state for r in rows} == {"known"}
        assert {r.word for r in rows} == {"你", "好", "今天"}
    finally:
        db.close()
