"""
SSRF guard for /api/extract: every redirect hop is re-validated and the
connection goes to the IP address that passed validation (no second DNS
lookup that could be answered differently).
"""

import socket

import pytest
from fastapi.testclient import TestClient

from app.services import safe_fetch

PUBLIC_IP = "93.184.216.34"


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = headers or {}
        self._body = body

    def read(self, amt=None):
        return self._body if amt is None else self._body[:amt]

    def release_conn(self):
        pass

    def close(self):
        pass


@pytest.fixture
def fake_dns(monkeypatch):
    table = {
        "example.com": [PUBLIC_IP],
        "news.example.org": ["203.0.113.10"],  # TEST-NET-3, reserved → treated as public here
        "intranet.example.com": ["10.1.2.3"],
        "rebind.example.com": ["8.8.8.8", "127.0.0.1"],
    }

    def _getaddrinfo(host, port, *args, **kwargs):
        if host not in table:
            raise socket.gaierror("unknown host")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0)) for ip in table[host]]

    monkeypatch.setattr(safe_fetch.socket, "getaddrinfo", _getaddrinfo)
    # 203.0.113.0/24 is documentation space; let it count as public so the
    # redirect tests have a second public host to bounce through.
    real_blocked = safe_fetch._is_blocked
    monkeypatch.setattr(
        safe_fetch,
        "_is_blocked",
        lambda ip: False if str(ip).startswith("203.0.113.") else real_blocked(ip),
    )
    return table


@pytest.fixture
def opener(monkeypatch):
    calls = []
    responses = []

    def _open(scheme, ip, port, host, path, timeout):
        calls.append({"scheme": scheme, "ip": ip, "port": port, "host": host, "path": path})
        return responses.pop(0)

    monkeypatch.setattr(safe_fetch, "_open", _open)
    return calls, responses


def test_connects_to_the_validated_ip(fake_dns, opener):
    calls, responses = opener
    responses.append(FakeResponse(200, {"Content-Type": "text/html"}, b"<p>hi</p>"))
    result = safe_fetch.fetch("https://example.com/a?b=1")
    assert result.body == b"<p>hi</p>"
    assert calls == [
        {"scheme": "https", "ip": PUBLIC_IP, "port": 443, "host": "example.com", "path": "/a?b=1"}
    ]


def test_redirect_to_loopback_is_blocked(fake_dns, opener):
    calls, responses = opener
    responses.append(FakeResponse(302, {"Location": "http://127.0.0.1/admin"}))
    with pytest.raises(safe_fetch.UnsafeUrlError):
        safe_fetch.fetch("https://example.com/")
    assert len(calls) == 1


def test_redirect_to_private_hostname_is_blocked(fake_dns, opener):
    calls, responses = opener
    responses.append(FakeResponse(301, {"Location": "http://intranet.example.com/"}))
    with pytest.raises(safe_fetch.UnsafeUrlError):
        safe_fetch.fetch("https://example.com/")
    assert len(calls) == 1


def test_host_with_any_private_record_is_blocked(fake_dns, opener):
    calls, _ = opener
    with pytest.raises(safe_fetch.UnsafeUrlError):
        safe_fetch.fetch("http://rebind.example.com/")
    assert calls == []


def test_follows_public_redirects(fake_dns, opener):
    calls, responses = opener
    responses.append(FakeResponse(302, {"Location": "https://news.example.org/story"}))
    responses.append(FakeResponse(301, {"Location": "/story/2"}))
    responses.append(FakeResponse(200, {}, b"body"))
    result = safe_fetch.fetch("http://example.com/")
    assert result.body == b"body"
    assert result.url == "https://news.example.org/story/2"
    assert [c["ip"] for c in calls] == [PUBLIC_IP, "203.0.113.10", "203.0.113.10"]
    assert calls[2]["path"] == "/story/2"


def test_too_many_redirects(fake_dns, opener):
    _, responses = opener
    for _ in range(safe_fetch.MAX_REDIRECTS + 1):
        responses.append(FakeResponse(302, {"Location": "/loop"}))
    with pytest.raises(safe_fetch.FetchFailed):
        safe_fetch.fetch("https://example.com/")


def test_body_is_capped(fake_dns, opener):
    _, responses = opener
    responses.append(FakeResponse(200, {}, b"x" * 100))
    result = safe_fetch.fetch("https://example.com/", max_bytes=10)
    assert result.body == b"x" * 10


def test_extract_endpoint_blocks_redirect_to_loopback(app_module, fake_dns, opener):
    from app.auth import require_auth
    from app.database import User

    _, responses = opener
    responses.append(FakeResponse(302, {"Location": "http://127.0.0.1:5001/api/admin"}))
    app_module.dependency_overrides[require_auth] = lambda: User(id=1, username="alice")
    try:
        with TestClient(app_module) as c:
            r = c.post("/api/extract", json={"url": "https://example.com/"})
    finally:
        app_module.dependency_overrides.clear()
    assert r.status_code == 400


# ---- blocking work stays off the event loop -------------------------------


def _assert_no_running_loop():
    import asyncio

    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()


def test_extract_handler_is_sync():
    import inspect

    from app.routers import extract

    assert not inspect.iscoroutinefunction(extract.extract_article)


def test_document_parse_runs_in_a_worker_thread(app_module, monkeypatch):
    from app.auth import require_auth
    from app.database import User
    from app.routers import extract
    from app.services.document_import import DocumentImportError

    seen = []

    def _parse(filename, data):
        _assert_no_running_loop()
        seen.append(filename)
        raise DocumentImportError("not a book")

    monkeypatch.setattr(extract, "extract_document", _parse)
    app_module.dependency_overrides[require_auth] = lambda: User(id=1, username="alice")
    try:
        with TestClient(app_module) as c:
            r = c.post("/api/extract/file", files={"file": ("a.epub", b"PK..", "application/epub")})
    finally:
        app_module.dependency_overrides.clear()
    assert r.status_code == 422
    assert seen == ["a.epub"]


def test_youtube_fetch_runs_in_a_worker_thread(app_module, monkeypatch):
    from app.auth import require_auth
    from app.database import User
    from app.routers import media
    from app.services.youtube_captions import YoutubeCaptionError

    seen = []

    def _fetch(video_id):
        _assert_no_running_loop()
        seen.append(video_id)
        raise YoutubeCaptionError("no captions")

    monkeypatch.setattr(media, "fetch_captioned_sentences", _fetch)
    app_module.dependency_overrides[require_auth] = lambda: User(id=1, username="alice")
    try:
        with TestClient(app_module) as c:
            r = c.post(
                "/api/media/youtube", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
            )
    finally:
        app_module.dependency_overrides.clear()
    assert r.status_code == 422
    assert seen == ["dQw4w9WgXcQ"]
