"""Pytest fixtures shared across the test suite."""

import os

import pytest

# These must be set BEFORE importing the app — main.py reads them at import time.
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ALLOWED_ORIGINS", "*")


@pytest.fixture(scope="session")
def app_module():
    """Import and return the FastAPI app, without running its startup event."""
    from app.main import app

    return app


@pytest.fixture
def client(app_module):
    """Synchronous TestClient — does NOT trigger startup_event."""
    from fastapi.testclient import TestClient

    with TestClient(app_module) as c:
        yield c


@pytest.fixture
def tmp_data_dir(monkeypatch, tmp_path):
    """Redirect app.core.paths.DATA_DIR to a temp dir for tests that write to disk."""
    from app.core import paths

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "backups").mkdir(parents=True, exist_ok=True)
    return tmp_path / "data"
