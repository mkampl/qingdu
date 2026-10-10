"""GET /api/vocabulary-lists/{id} — the detail page loads one list instead
of every list with every word."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user, require_auth
from app.database import Base, User, VocabularyList, get_db


@pytest.fixture
def client(app_module):
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
    db.add(
        VocabularyList(
            id=5,
            user_id=1,
            name="Lesson",
            list_type="custom",
            apply_as_glossary=True,
            sections=json.dumps(
                [
                    {"name": "Main", "words": [{"hanzi": "你好", "meaning": "hello"}]},
                    {"name": "Empty", "words": []},
                ]
            ),
        )
    )
    db.add(VocabularyList(id=6, user_id=2, name="Bob's", list_type="custom", sections="[]"))
    db.commit()
    db.close()

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    def _user():
        s = Session()
        try:
            return s.query(User).filter(User.id == 1).first()
        finally:
            s.close()

    app_module.dependency_overrides[get_db] = _db
    app_module.dependency_overrides[require_auth] = _user
    app_module.dependency_overrides[get_current_user] = _user
    try:
        with TestClient(app_module) as c:
            yield c
    finally:
        app_module.dependency_overrides.clear()


def test_get_single_list(client):
    r = client.get("/api/vocabulary-lists/5")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 5
    assert body["name"] == "Lesson"
    assert body["type"] == "custom"
    assert body["apply_as_glossary"] is True
    assert [s["name"] for s in body["sections"]] == ["Main", "Empty"]
    assert body["sections"][0]["words"][0]["hanzi"] == "你好"


def test_get_single_list_matches_list_endpoint(client):
    one = client.get("/api/vocabulary-lists/5").json()
    all_lists = client.get("/api/vocabulary-lists").json()
    assert all_lists == [one]


def test_get_other_users_list_is_404(client):
    assert client.get("/api/vocabulary-lists/6").status_code == 404
    assert client.get("/api/vocabulary-lists/999").status_code == 404
