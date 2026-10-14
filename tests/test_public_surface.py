"""Endpoints that used to be public and are gone or admin-only now."""

from app.auth import get_current_user, require_auth
from app.database import User


def test_bulk_dictionary_dumps_are_gone(client):
    for path in (
        "/api/get-hsk-vocabulary",
        "/api/get-hsk-lists-original",
        "/api/debug/vocab-sample",
    ):
        assert client.get(path).status_code == 404, path


def test_vocab_lookup_needs_an_admin(client, app_module):
    assert client.get("/api/debug/vocab-lookup/好").status_code == 401

    def user(admin):
        return lambda: User(id=1, username="u", password_hash="x", is_admin=admin)

    try:
        app_module.dependency_overrides[require_auth] = user(False)
        app_module.dependency_overrides[get_current_user] = user(False)
        assert client.get("/api/debug/vocab-lookup/好").status_code == 403
        app_module.dependency_overrides[require_auth] = user(True)
        assert client.get("/api/debug/vocab-lookup/好").status_code == 200
    finally:
        app_module.dependency_overrides.clear()


def test_hanzi_test_page_is_not_served(client):
    assert client.get("/static/hanzi-test.html").status_code == 404
