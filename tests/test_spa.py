"""
SPA catch-all (app/routers/spa.py): history-mode routes get index.html,
but API / static / asset paths that matched nothing must 404 instead of
answering 200 text/html (which surfaced as `Unexpected token '<'` in the
client and made `curl /api/health` look healthy).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import spa


@pytest.fixture
def spa_client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Qingdu</title>")
    (dist / "robots.txt").write_text("User-agent: *")
    monkeypatch.setattr(spa, "SPA_DIST", dist)
    monkeypatch.setattr(spa, "SPA_ASSETS", dist / "assets")

    app = FastAPI()

    @app.get("/api/real")
    def real():
        return {"ok": True}

    spa.mount(app)
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    [
        "/api",
        "/api/",
        "/api/does-not-exist",
        "/api/health",
        "/static/nope.js",
        "/assets/missing-abc123.js",
        "/health/extra",
    ],
)
def test_unknown_backend_paths_404_as_json(spa_client, path):
    r = spa_client.get(path)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/", "/review", "/vocab/5", "/texts?x=1", "/apiary"])
def test_client_routes_get_the_shell(spa_client, path):
    r = spa_client.get(path)
    assert r.status_code == 200
    assert "Qingdu" in r.text


def test_root_files_and_real_routes_still_served(spa_client):
    assert spa_client.get("/robots.txt").text == "User-agent: *"
    assert spa_client.get("/api/real").json() == {"ok": True}
