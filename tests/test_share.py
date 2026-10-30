"""
Public share endpoints for saved texts — token mint, public fetch, revoke,
404 behaviour. Bypasses auth via dependency-override the same way the
words tests do.
"""

import json
import uuid

import pytest

from app.database import SavedText, User


@pytest.fixture
def share_client(memory_db, open_client):
    TestingSession = memory_db

    db = TestingSession()
    db.add(User(id=1, username="alice", password_hash="x", invite_quota=0))
    db.add(User(id=2, username="bob", password_hash="x", invite_quota=0))
    db.add(
        SavedText(
            id=10,
            user_id=1,
            title="Test text",
            content="你好世界。",
            analysis_data=json.dumps(
                {"words": [{"text": "你好", "is_hsk": True}], "statistics": {}}
            ),
        )
    )
    # Bob's text — alice shouldn't be able to share it.
    db.add(
        SavedText(
            id=11,
            user_id=2,
            title="Bob's text",
            content="再见。",
            analysis_data=json.dumps({"words": [], "statistics": {}}),
        )
    )
    db.commit()
    db.close()

    # Signed in as alice; bob's text is the cross-tenant decoy.
    return open_client(TestingSession), TestingSession


def test_enable_share_mints_token(share_client):
    client, _ = share_client
    r = client.post("/api/texts/10/share")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "token" in body
    # UUID4 — must parse cleanly.
    uuid.UUID(body["token"])


def test_enable_share_is_idempotent(share_client):
    client, _ = share_client
    a = client.post("/api/texts/10/share").json()["token"]
    b = client.post("/api/texts/10/share").json()["token"]
    assert a == b, "second call should return the same token"


def test_public_fetch_returns_analysis(share_client):
    client, _ = share_client
    token = client.post("/api/texts/10/share").json()["token"]
    r = client.get(f"/api/share/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Test text"
    assert body["content"] == "你好世界。"
    assert body["analysisData"] is not None
    # No leak of internal fields.
    assert "user_id" not in body
    assert "reading_progress" not in body


def test_revoke_breaks_the_link(share_client):
    client, _ = share_client
    token = client.post("/api/texts/10/share").json()["token"]
    client.delete("/api/texts/10/share")
    r = client.get(f"/api/share/{token}")
    assert r.status_code == 404


def test_cannot_share_someone_elses_text(share_client):
    client, _ = share_client
    # Bob's text id=11; alice is the auth'd user. Expect 404.
    r = client.post("/api/texts/11/share")
    assert r.status_code == 404


def test_unknown_token_404s(share_client):
    client, _ = share_client
    r = client.get("/api/share/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
