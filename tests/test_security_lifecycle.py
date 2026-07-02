"""
Security- and lifecycle-critical paths that shipped untested until the
2026-07 audit — and promptly contained a data-retention bug: deleting a
user who had ever created an invitation raised IntegrityError, rolled
back, and made the lifecycle hard-delete sweep silently delete nobody.

Covers: user deletion cascades, the dormant->deleted two-pass guarantee,
admin authorization, the math captcha, per-IP signup limiting, and the
SSRF guard on the URL extractor.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base,
    InvitationToken,
    SavedText,
    SignupAttempt,
    User,
    UserWord,
    UserWordEvent,
    VocabularyList,
)
from app.services import captcha, lifecycle


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    yield session
    session.close()


def _make_user(db, username, **kwargs):
    user = User(username=username, password_hash="x", invite_quota=0, **kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---- deletion cascades -------------------------------------------------


def test_purge_user_with_invitations_and_data(db_session):
    """The audit's BLOCKER: created_invitations had no cascade, so deleting
    an invite-creator tried to NULL a NOT NULL FK and rolled back."""
    db = db_session
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")

    # Alice created two invitations; Bob claimed one of them.
    inv_open = InvitationToken(
        token="tok-open",
        created_by_user_id=alice.id,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    inv_claimed = InvitationToken(
        token="tok-claimed",
        created_by_user_id=alice.id,
        claimed_by_user_id=bob.id,
        claimed_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.add_all([inv_open, inv_claimed])
    # Plus the usual satellite data.
    db.add(SavedText(user_id=alice.id, title="t", content="x", analysis_data="{}"))
    db.add(VocabularyList(user_id=alice.id, name="l", list_type="custom", sections="[]"))
    db.add(UserWord(user_id=alice.id, word="你好", state="learning"))
    db.add(UserWordEvent(user_id=alice.id, word="你好", event_type="seen"))
    db.commit()

    lifecycle.purge_user(db, alice)
    db.commit()  # must not raise IntegrityError

    assert db.query(User).filter(User.username == "alice").first() is None
    assert db.query(InvitationToken).count() == 0
    assert db.query(SavedText).count() == 0
    assert db.query(VocabularyList).count() == 0
    assert db.query(UserWord).count() == 0
    assert db.query(UserWordEvent).count() == 0
    # Bob survives his invite's deletion.
    assert db.query(User).filter(User.username == "bob").first() is not None


def test_purge_claimer_nulls_claim_keeps_token(db_session):
    db = db_session
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    db.add(
        InvitationToken(
            token="tok",
            created_by_user_id=alice.id,
            claimed_by_user_id=bob.id,
            claimed_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
    )
    db.commit()

    lifecycle.purge_user(db, bob)
    db.commit()

    token = db.query(InvitationToken).one()
    assert token.claimed_by_user_id is None
    assert token.created_by_user_id == alice.id


# ---- lifecycle sweep ---------------------------------------------------


def _lifecycle_settings(db, soft_days, hard_days):
    lifecycle.set_settings(
        db,
        {
            "lifecycle.soft_delete_days": soft_days,
            "lifecycle.hard_delete_days": hard_days,
        },
    )


def test_lifecycle_dormant_then_delete_needs_two_passes(db_session):
    """An account past BOTH thresholds must still see the dormant warning
    state for one interval before deletion — never active -> gone in one
    pass (e.g. after the server was offline for months)."""
    db = db_session
    stale = _make_user(db, "stale")
    stale.last_active = datetime.utcnow() - timedelta(days=400)
    # An invitation, so this test also exercises the cascade in the sweep.
    db.add(
        InvitationToken(
            token="tok-stale",
            created_by_user_id=stale.id,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
    )
    db.commit()
    _lifecycle_settings(db, soft_days=30, hard_days=90)

    stats = lifecycle.run_lifecycle_pass(db)
    assert stats["soft_marked"] == 1
    assert stats["hard_deleted"] == 0
    assert db.query(User).filter(User.username == "stale").one().account_status == "dormant"

    stats = lifecycle.run_lifecycle_pass(db)
    assert stats["hard_deleted"] == 1
    assert db.query(User).filter(User.username == "stale").first() is None
    assert db.query(InvitationToken).count() == 0


def test_lifecycle_never_touches_admins(db_session):
    db = db_session
    root = _make_user(db, "root", is_admin=True)
    root.last_active = datetime.utcnow() - timedelta(days=400)
    db.commit()
    _lifecycle_settings(db, soft_days=30, hard_days=90)

    lifecycle.run_lifecycle_pass(db)
    lifecycle.run_lifecycle_pass(db)

    root = db.query(User).filter(User.username == "root").one()
    assert root.account_status == "active"


# ---- admin authorization ----------------------------------------------


@pytest.fixture
def user_client(app_module, db_session):
    """TestClient authenticated as a plain (non-admin) user."""
    from fastapi.testclient import TestClient

    from app.auth import get_current_user
    from app.database import get_db

    plain = _make_user(db_session, "plain")

    app_module.dependency_overrides[get_db] = lambda: iter([db_session])
    app_module.dependency_overrides[get_current_user] = lambda: plain
    with TestClient(app_module) as c:
        yield c
    app_module.dependency_overrides.clear()


def test_admin_endpoints_forbid_non_admins(user_client):
    assert user_client.get("/api/admin/users").status_code == 403
    assert user_client.delete("/api/admin/users/1").status_code == 403
    assert user_client.get("/api/admin/registration-settings").status_code == 403
    assert user_client.patch("/api/admin/registration-settings", json={}).status_code == 403


# ---- captcha -----------------------------------------------------------


def test_captcha_round_trip():
    pair = captcha.issue()
    a, op, b = pair["question"].split()
    expected = int(a) + int(b) if op == "+" else int(a) - int(b)

    assert captcha.verify(pair["token"], expected)
    assert captcha.verify(pair["token"], str(expected))  # string form too
    assert not captcha.verify(pair["token"], expected + 1)
    assert not captcha.verify(pair["token"], None)
    assert not captcha.verify("", expected)
    assert not captcha.verify("garbage.jwt.token", expected)


def test_captcha_rejects_foreign_jwt():
    """A validly-signed NON-captcha JWT (e.g. a stolen auth token) must not
    pass the captcha gate."""
    from app.auth import create_access_token

    token = create_access_token(data={"sub": "alice", "a": 7})
    assert not captcha.verify(token, 7)


# ---- signup rate limiting ----------------------------------------------


def test_signup_blocked_when_closed(db_session):
    lifecycle.set_settings(db_session, {"registration.open": False})
    with pytest.raises(lifecycle.SignupBlocked) as exc:
        lifecycle.check_signup_allowed(db_session, "1.2.3.4")
    assert exc.value.code == "closed"


def test_signup_per_ip_limit(db_session):
    db = db_session
    lifecycle.set_settings(db, {"registration.open": True, "registration.per_ip_24h": 3})
    for _ in range(3):
        lifecycle.check_signup_allowed(db, "9.9.9.9")
        lifecycle.record_attempt(db, "9.9.9.9", successful=True)

    with pytest.raises(lifecycle.SignupBlocked) as exc:
        lifecycle.check_signup_allowed(db, "9.9.9.9")
    assert exc.value.code == "ip_rate_limited"
    # A different IP is unaffected.
    lifecycle.check_signup_allowed(db, "8.8.8.8")


def test_signup_global_daily_cap(db_session):
    db = db_session
    lifecycle.set_settings(
        db,
        {
            "registration.open": True,
            "registration.per_ip_24h": 100,
            "registration.daily_cap": 2,
        },
    )
    db.add(SignupAttempt(ip_address="1.1.1.1", successful=True))
    db.add(SignupAttempt(ip_address="2.2.2.2", successful=True))
    db.commit()

    with pytest.raises(lifecycle.SignupBlocked) as exc:
        lifecycle.check_signup_allowed(db, "3.3.3.3")
    assert exc.value.code == "daily_cap_reached"


# ---- SSRF guard ---------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:8000/api/health",
        "http://10.0.0.5/",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://[::1]/",
        "ftp://example.com/file",
        "file:///etc/passwd",
    ],
)
def test_extract_url_guard_rejects_internal_targets(url):
    from app.routers.extract import _validate_url

    with pytest.raises(HTTPException) as exc:
        _validate_url(url)
    assert exc.value.status_code == 400
