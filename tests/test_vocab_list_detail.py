"""GET /api/vocabulary-lists/{id} — the detail page loads one list instead
of every list with every word."""

import json

import pytest

from app.database import User, VocabularyList


@pytest.fixture
def client(memory_db, open_client):
    Session = memory_db

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

    return open_client(Session)


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
