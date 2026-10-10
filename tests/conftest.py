"""Pytest fixtures shared across the test suite."""

import os

import pytest

# These must be set BEFORE importing the app — main.py reads them at import time.
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
# Skip the ~4 MB CC-CEDICT download on every CI run. Tests that need
# cedict_vocab populated populate it directly via the state module;
# the (small handful) that test lookup chains involving cedict have
# their own fixtures that clear + seed.
os.environ.setdefault("QINGDU_SKIP_CEDICT_LOAD", "1")
# Phase 2.7 — disable the background lifecycle scheduler under tests so its
# asyncio task doesn't outlive the TestClient context. See main.py shutdown
# handler for the corresponding cleanup path.
os.environ.setdefault("QINGDU_SKIP_SCHEDULER", "1")


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


@pytest.fixture(autouse=True)
def _reset_cloze_miss_cache():
    """The cloze service remembers sentence misses per user id in memory;
    every test builds its own database, so start each one clean."""
    from app.services import cloze

    cloze.forget_misses()
    yield
    cloze.forget_misses()


@pytest.fixture
def no_learner_glosses(monkeypatch, tmp_path):
    """Parse dictionaries without app/data/learner_glosses.json, for tests
    of the CC-CEDICT reading and sense selection underneath it. The app
    always loads the learner layer; tests about what the user sees should
    keep it."""
    from app.services import learner_glosses

    monkeypatch.setattr(learner_glosses, "LEARNER_GLOSSES_FILE", tmp_path / "no-glosses.json")


@pytest.fixture(scope="module")
def pinned_dictionaries():
    """Load the vendored HSK list and CC-CEDICT exactly as startup does,
    then put the previous shared state back."""
    from app import state
    from app.services import dict_data

    saved = (
        dict(state.hsk_vocab),
        dict(state.hsk_lists_original),
        dict(state.cedict_vocab),
    )
    dict_data.load_pinned_dictionaries()
    yield
    for target, copy in zip(
        (state.hsk_vocab, state.hsk_lists_original, state.cedict_vocab), saved, strict=True
    ):
        target.clear()
        target.update(copy)
