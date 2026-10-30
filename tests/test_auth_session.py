"""Session hygiene: credential re-checks, token_version revocation, and the
shared username/password rules for every account-creation path.

Real in-memory DB and real JWTs — the point is the auth plumbing itself,
so nothing here overrides get_current_user.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import (
    create_access_token,
    create_session_token,
    generate_api_token,
    get_password_hash,
    hash_api_token,
)
from app.core.rate_limit import limiter
from app.database import ApiToken, Base, InvitationToken, User, get_db

PASSWORD = "correct-horse"


@pytest.fixture
def auth_client(app_module):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()
    db.add_all(
        [
            User(
                id=1,
                username="alice",
                password_hash=get_password_hash(PASSWORD),
                is_admin=False,
                must_change_password=False,
            ),
            User(
                id=2,
                username="root",
                password_hash=get_password_hash(PASSWORD),
                is_admin=True,
                must_change_password=False,
            ),
        ]
    )
    db.commit()
    db.close()

    def _override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app_module.dependency_overrides[get_db] = _override_get_db
    limiter.reset()
    try:
        with TestClient(app_module) as c:
            c.session_factory = TestingSession  # type: ignore[attr-defined]
            yield c
    finally:
        app_module.dependency_overrides.clear()


def _login(client, username="alice", password=PASSWORD) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _me(client, token: str) -> bool:
    r = client.get("/api/auth/me", headers=_h(token))
    assert r.status_code == 200
    return r.json()["authenticated"]


# ---- wrong credentials on re-check are 403, session survives -------------


def test_wrong_old_password_is_403_and_session_survives(auth_client):
    token = _login(auth_client)
    r = auth_client.post(
        "/api/auth/change-password",
        json={"old_password": "nope-nope", "new_password": "another-pass"},
        headers=_h(token),
    )
    assert r.status_code == 403
    assert _me(auth_client, token)


def test_wrong_delete_account_password_is_403(auth_client):
    token = _login(auth_client)
    r = auth_client.request(
        "DELETE", "/api/auth/me", json={"password": "nope-nope"}, headers=_h(token)
    )
    assert r.status_code == 403
    assert _me(auth_client, token)


# ---- token_version -----------------------------------------------------


def test_password_change_invalidates_old_tokens(auth_client):
    other_device = _login(auth_client)
    this_device = _login(auth_client)
    r = auth_client.post(
        "/api/auth/change-password",
        json={"old_password": PASSWORD, "new_password": "another-pass"},
        headers=_h(this_device),
    )
    assert r.status_code == 200
    fresh = r.json()["access_token"]

    assert not _me(auth_client, other_device)
    assert not _me(auth_client, this_device)
    assert _me(auth_client, fresh)
    assert auth_client.get("/api/words/state", headers=_h(other_device)).status_code == 401


def test_admin_reset_invalidates_user_tokens(auth_client):
    alice = _login(auth_client)
    admin = _login(auth_client, "root")
    r = auth_client.post(
        "/api/admin/users/1/reset-password",
        json={"new_password": "reset-pass-1"},
        headers=_h(admin),
    )
    assert r.status_code == 200
    assert not _me(auth_client, alice)
    assert _me(auth_client, admin)


def test_admin_reset_rejects_bad_body(auth_client):
    alice = _login(auth_client)
    admin = _login(auth_client, "root")
    url = "/api/admin/users/1/reset-password"
    assert auth_client.post(url, json={}, headers=_h(admin)).status_code == 422
    assert (
        auth_client.post(url, json={"new_password": 12345678}, headers=_h(admin)).status_code == 422
    )
    assert (
        auth_client.post(url, json={"new_password": "short"}, headers=_h(admin)).status_code == 400
    )
    assert _me(auth_client, alice)


def test_token_without_version_claim_is_rejected(auth_client):
    legacy = create_access_token({"sub": "alice"})
    assert not _me(auth_client, legacy)
    assert auth_client.get("/api/external/words", headers=_h(legacy)).status_code == 401


def test_token_with_current_version_is_accepted(auth_client):
    db = auth_client.session_factory()
    user = db.get(User, 1)
    assert _me(auth_client, create_session_token(user))
    db.close()


def test_pat_survives_password_change(auth_client):
    raw = generate_api_token()
    db = auth_client.session_factory()
    db.add(
        ApiToken(
            user_id=1,
            name="companion",
            token_hash=hash_api_token(raw),
            token_prefix=raw[:10],
            scopes="read:words",
        )
    )
    db.commit()
    db.close()

    token = _login(auth_client)
    r = auth_client.post(
        "/api/auth/change-password",
        json={"old_password": PASSWORD, "new_password": "another-pass"},
        headers=_h(token),
    )
    assert r.status_code == 200
    assert auth_client.get("/api/external/words", headers=_h(raw)).status_code == 200


# ---- same credential rules everywhere ------------------------------------


def _invite(client) -> str:
    db = client.session_factory()
    db.add(
        InvitationToken(
            token="inv-123",
            created_by_user_id=2,
            expires_at=datetime.utcnow() + timedelta(days=1),
        )
    )
    db.commit()
    db.close()
    return "inv-123"


@pytest.mark.parametrize(
    "username,password",
    [("bob", "short"), ("b", "long-enough-pw"), ("bob smith", "long-enough-pw")],
)
def test_invite_signup_enforces_credential_rules(auth_client, username, password):
    token = _invite(auth_client)
    r = auth_client.post(
        "/api/auth/signup-with-invite",
        json={"token": token, "username": username, "password": password},
    )
    assert r.status_code == 400


def test_invite_signup_accepts_valid_credentials(auth_client):
    token = _invite(auth_client)
    r = auth_client.post(
        "/api/auth/signup-with-invite",
        json={"token": token, "username": "bob", "password": "long-enough-pw"},
    )
    assert r.status_code == 200, r.text
    assert _me(auth_client, r.json()["access_token"])


@pytest.mark.parametrize(
    "username,password",
    [("carol", "short"), ("c!", "long-enough-pw")],
)
def test_admin_create_user_enforces_credential_rules(auth_client, username, password):
    admin = _login(auth_client, "root")
    r = auth_client.post(
        "/api/admin/users",
        json={"username": username, "password": password},
        headers=_h(admin),
    )
    assert r.status_code == 400


def _ticket(client, token: str, path: str):
    return client.post("/api/auth/download-ticket", json={"path": path}, headers=_h(token))


def test_download_ticket_opens_its_download_only(auth_client):
    token = _login(auth_client)
    r = _ticket(auth_client, token, "/api/words/export.csv")
    assert r.status_code == 200
    ticket = r.json()["ticket"]
    assert auth_client.get(f"/api/words/export.csv?ticket={ticket}").status_code == 200
    # Another download, or the ticket used as a session token, is refused.
    assert auth_client.get(f"/api/auth/export?ticket={ticket}").status_code == 401
    assert auth_client.get("/api/words/state", headers=_h(ticket)).status_code == 401


def test_download_ticket_only_for_downloads(auth_client):
    token = _login(auth_client)
    assert _ticket(auth_client, token, "/api/auth/me").status_code == 400
    assert _ticket(auth_client, token, "/api/vocabulary-lists/3/export").status_code == 200


def test_download_ticket_dies_with_the_session(auth_client):
    token = _login(auth_client)
    ticket = _ticket(auth_client, token, "/api/words/export.csv").json()["ticket"]
    r = auth_client.post(
        "/api/auth/change-password",
        json={"old_password": PASSWORD, "new_password": PASSWORD + "x"},
        headers=_h(token),
    )
    assert r.status_code == 200
    assert auth_client.get(f"/api/words/export.csv?ticket={ticket}").status_code == 401
