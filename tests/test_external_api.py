"""
Personal access tokens and the external read/write vocab API.

Uses a real in-memory DB (not dependency-overridden auth) so the actual
JWT-vs-PAT branch in app.auth.require_api_scope gets exercised, along with
real token hashing and scope checks.
"""

from app.auth import create_access_token, generate_api_token, hash_api_token
from app.database import ApiToken, UserWord


def _mint_token(client, *, scopes: str) -> str:
    """Insert an ApiToken row directly (bypassing the /api/tokens endpoint,
    which is JWT-only) and return the raw bearer token."""
    raw = generate_api_token()
    db = client.session_factory()
    db.add(
        ApiToken(
            user_id=1,
            name="test token",
            token_hash=hash_api_token(raw),
            token_prefix=raw[:10],
            scopes=scopes,
        )
    )
    db.commit()
    db.close()
    return raw


def _jwt(username="alice") -> str:
    return create_access_token({"sub": username, "tv": 0})


def test_pat_without_scope_is_rejected(ext_client):
    token = _mint_token(ext_client, scopes="write:words")
    r = ext_client.get("/api/external/words", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_pat_with_scope_reads_words(ext_client):
    token = _mint_token(ext_client, scopes="read:words")
    db = ext_client.session_factory()
    db.add(UserWord(user_id=1, word="你好", state="known", pinyin="nǐ hǎo", meaning="hello"))
    db.commit()
    db.close()

    r = ext_client.get("/api/external/words", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    words = r.json()["words"]
    assert len(words) == 1
    assert words[0]["word"] == "你好"
    assert words[0]["state"] == "known"


def test_pat_filters_by_state(ext_client):
    token = _mint_token(ext_client, scopes="read:words")
    db = ext_client.session_factory()
    db.add(UserWord(user_id=1, word="一", state="known"))
    db.add(UserWord(user_id=1, word="二", state="learning"))
    db.commit()
    db.close()

    r = ext_client.get(
        "/api/external/words",
        params={"state": "known"},
        headers={"Authorization": f"Bearer {token}"},
    )
    words = r.json()["words"]
    assert [w["word"] for w in words] == ["一"]


def test_revoked_token_is_rejected(ext_client):
    token = _mint_token(ext_client, scopes="read:words")
    db = ext_client.session_factory()
    from datetime import datetime

    row = db.query(ApiToken).filter(ApiToken.user_id == 1).first()
    row.revoked_at = datetime.utcnow()
    db.commit()
    db.close()

    r = ext_client.get("/api/external/words", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_unknown_token_is_rejected(ext_client):
    r = ext_client.get(
        "/api/external/words", headers={"Authorization": "Bearer qd_not-a-real-token"}
    )
    assert r.status_code == 401


def test_jwt_session_bypasses_scope_check(ext_client):
    """A logged-in browser session (JWT) has full access regardless of
    scopes — scopes only constrain narrowly-issued PATs."""
    r = ext_client.get("/api/external/words", headers={"Authorization": f"Bearer {_jwt()}"})
    assert r.status_code == 200


def test_report_encountered_words_creates_learning_rows(ext_client):
    token = _mint_token(ext_client, scopes="write:words")
    r = ext_client.post(
        "/api/external/words/encountered",
        json={"words": [{"word": "苹果", "source": "speaking-companion"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == ["苹果"]

    db = ext_client.session_factory()
    row = db.query(UserWord).filter(UserWord.user_id == 1, UserWord.word == "苹果").first()
    assert row.state == "learning"
    db.close()


def test_report_encountered_words_never_downgrades_known(ext_client):
    token = _mint_token(ext_client, scopes="write:words")
    db = ext_client.session_factory()
    db.add(UserWord(user_id=1, word="谢谢", state="known"))
    db.commit()
    db.close()

    r = ext_client.post(
        "/api/external/words/encountered",
        json={"words": [{"word": "谢谢"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["accepted"] == []

    db = ext_client.session_factory()
    row = db.query(UserWord).filter(UserWord.user_id == 1, UserWord.word == "谢谢").first()
    assert row.state == "known"
    db.close()


def test_token_management_is_jwt_only_not_pat(ext_client):
    """A PAT (even with every scope) must not be able to mint or list more
    tokens — token management stays session-only."""
    token = _mint_token(ext_client, scopes="read:words write:words")
    r = ext_client.get("/api/tokens", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_create_list_and_revoke_token_via_session(ext_client):
    jwt = _jwt()
    r = ext_client.post(
        "/api/tokens",
        json={"name": "companion app", "scopes": ["read:words", "write:words"]},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"].startswith("qd_")
    token_id = body["id"]

    r = ext_client.get("/api/tokens", headers={"Authorization": f"Bearer {jwt}"})
    names = [t["name"] for t in r.json()["tokens"]]
    assert "companion app" in names

    r = ext_client.delete(f"/api/tokens/{token_id}", headers={"Authorization": f"Bearer {jwt}"})
    assert r.status_code == 200

    r = ext_client.get("/api/tokens", headers={"Authorization": f"Bearer {jwt}"})
    assert r.json()["tokens"] == []


def test_create_token_rejects_unknown_scope(ext_client):
    r = ext_client.post(
        "/api/tokens",
        json={"name": "bad", "scopes": ["delete:everything"]},
        headers={"Authorization": f"Bearer {_jwt()}"},
    )
    assert r.status_code == 400
