"""GET /api/vocab/hsk?state=… — filter the HSK catalog by the user's word
state ("which HSK 3 words do I know?") and report per-state counts."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import state
from app.auth import get_current_user, require_auth
from app.database import Base, User, UserWord, get_db

VOCAB = {
    "你": {"pinyin": "nǐ", "meaning": "you", "level_new": "new-1", "level_old": "old-1"},
    "好": {"pinyin": "hǎo", "meaning": "good", "level_new": "new-1", "level_old": "old-1"},
    "猫": {"pinyin": "māo", "meaning": "cat", "level_new": "new-3", "level_old": "old-2"},
    "狗": {"pinyin": "gǒu", "meaning": "dog", "level_new": "new-3", "level_old": "old-2"},
    "鸟": {"pinyin": "niǎo", "meaning": "bird", "level_new": "new-3", "level_old": "old-3"},
    "鱼": {"pinyin": "yú", "meaning": "fish", "level_new": "new-3", "level_old": "old-2"},
}
STATES = {"你": "known", "猫": "known", "狗": "learning", "鸟": "ignored"}


def _make_client(app_module, authed: bool):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    db.add(User(id=1, username="alice", password_hash="x", invite_quota=0))
    db.add(User(id=2, username="bob", password_hash="x", invite_quota=0))
    for word, st in STATES.items():
        db.add(UserWord(user_id=1, word=word, state=st, seen_count=1))
    # Another user's state must never leak into alice's filter.
    db.add(UserWord(user_id=2, word="鱼", state="known", seen_count=1))
    db.commit()
    db.close()

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    def _user():
        if not authed:
            return None
        s = Session()
        try:
            return s.query(User).filter(User.id == 1).first()
        finally:
            s.close()

    app_module.dependency_overrides[get_db] = _db
    app_module.dependency_overrides[get_current_user] = _user
    app_module.dependency_overrides[require_auth] = _user
    return TestClient(app_module)


@pytest.fixture
def client(app_module):
    c = _make_client(app_module, authed=True)
    try:
        with c:
            saved = dict(state.hsk_vocab)
            state.hsk_vocab.clear()
            state.hsk_vocab.update(VOCAB)
            try:
                yield c
            finally:
                state.hsk_vocab.clear()
                state.hsk_vocab.update(saved)
    finally:
        app_module.dependency_overrides.clear()


@pytest.fixture
def anon_client(app_module):
    c = _make_client(app_module, authed=False)
    try:
        with c:
            saved = dict(state.hsk_vocab)
            state.hsk_vocab.clear()
            state.hsk_vocab.update(VOCAB)
            try:
                yield c
            finally:
                state.hsk_vocab.clear()
                state.hsk_vocab.update(saved)
    finally:
        app_module.dependency_overrides.clear()


def _words(body):
    return sorted(i["hanzi"] for i in body["items"])


def test_known_words_of_one_level(client):
    body = client.get("/api/vocab/hsk", params={"level": "new-3", "state": "known"}).json()
    assert _words(body) == ["猫"]
    assert body["total"] == 1
    assert all(i["user_state"] == "known" for i in body["items"])


def test_new_means_no_state_row(client):
    body = client.get("/api/vocab/hsk", params={"level": "new-3", "state": "new"}).json()
    # 鱼 is known only for another user, so it is new for alice.
    assert _words(body) == ["鱼"]


def test_several_states_combine(client):
    body = client.get("/api/vocab/hsk", params={"state": "learning,known"}).json()
    assert _words(body) == ["你", "狗", "猫"]


def test_state_counts_follow_level_and_search_not_state(client):
    body = client.get("/api/vocab/hsk", params={"level": "new-3", "state": "known"}).json()
    assert body["state_counts"] == {"new": 1, "learning": 1, "known": 1, "ignored": 1}
    body = client.get("/api/vocab/hsk", params={"q": "d"}).json()  # good, dog, bird
    assert body["state_counts"] == {"new": 1, "learning": 1, "known": 0, "ignored": 1}


def test_filter_applies_before_paging(client):
    first = client.get("/api/vocab/hsk", params={"state": "new", "limit": 1}).json()
    second = client.get("/api/vocab/hsk", params={"state": "new", "offset": 1, "limit": 1}).json()
    assert first["total"] == second["total"] == 2
    assert sorted(_words(first) + _words(second)) == ["好", "鱼"]


def test_unknown_state_is_400(client):
    assert client.get("/api/vocab/hsk", params={"state": "mastered"}).status_code == 400


def test_anonymous_everything_is_new(anon_client):
    body = anon_client.get("/api/vocab/hsk", params={"level": "new-3"}).json()
    assert body["state_counts"] == {"new": 4, "learning": 0, "known": 0, "ignored": 0}
    body = anon_client.get("/api/vocab/hsk", params={"state": "known"}).json()
    assert body["total"] == 0
