"""
Client-IP derivation behind a reverse proxy (H3).

Behind Caddy every request reaches uvicorn from the Docker bridge gateway,
so keying rate limits on the socket peer turned the 5/minute login limit
into one global budget. uvicorn's ProxyHeadersMiddleware (driven by
FORWARDED_ALLOW_IPS) rewrites `request.client` from X-Forwarded-For when,
and only when, the peer is a trusted proxy. The app keys everything on
`request.client.host` and never reads the raw header itself, so a client
talking to the port directly can't spoof its way into a fresh budget.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.rate_limit import client_ip, limiter
from app.database import Base


def _request(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (peer, 12345)})


def test_client_ip_uses_socket_peer_not_raw_header():
    assert client_ip(_request("10.0.0.7", xff="1.2.3.4")) == "10.0.0.7"
    assert client_ip(_request("10.0.0.7")) == "10.0.0.7"


def test_client_ip_without_client():
    assert client_ip(Request({"type": "http", "headers": []})) == "unknown"


def test_limiter_and_signup_share_the_same_key():
    from app.routers import auth

    assert limiter._key_func is client_ip
    assert auth._client_ip is client_ip


@pytest.fixture
def login_app(app_module):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    from app.database import get_db

    def _get_db():
        yield session

    app_module.dependency_overrides[get_db] = _get_db
    limiter.reset()
    yield app_module
    limiter.reset()
    app_module.dependency_overrides.clear()
    session.close()


def _login(client, xff: str):
    return client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "wrong-password"},
        headers={"X-Forwarded-For": xff},
    )


def test_trusted_proxy_gives_each_client_its_own_login_budget(login_app):
    from fastapi.testclient import TestClient

    # TestClient's peer is "testclient"; trust it the way production trusts
    # the proxy in front of the container.
    with TestClient(ProxyHeadersMiddleware(login_app, trusted_hosts="testclient")) as c:
        for _ in range(5):
            assert _login(c, "203.0.113.10").status_code == 401
        assert _login(c, "203.0.113.10").status_code == 429
        # A different real client behind the same proxy is unaffected.
        assert _login(c, "203.0.113.11").status_code == 401


def test_untrusted_peer_cannot_spoof_forwarded_for(login_app):
    from fastapi.testclient import TestClient

    with TestClient(ProxyHeadersMiddleware(login_app, trusted_hosts="127.0.0.1")) as c:
        for i in range(5):
            assert _login(c, f"198.51.100.{i}").status_code == 401
        # Rotating the header doesn't buy a fresh budget.
        assert _login(c, "198.51.100.99").status_code == 429
