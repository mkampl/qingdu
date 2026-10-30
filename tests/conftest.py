"""Pytest fixtures shared across the test suite."""

import os
from contextlib import ExitStack

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# These must be set BEFORE importing the app — main.py reads them at import time.
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
# Skip loading CC-CEDICT at startup. Tests that need cedict_vocab seed it
# through the state module or load it with `pinned_dictionaries`.
os.environ.setdefault("QINGDU_SKIP_CEDICT_LOAD", "1")
# No background lifecycle scheduler under tests: its asyncio task would
# outlive the TestClient context.
os.environ.setdefault("QINGDU_SKIP_SCHEDULER", "1")


@pytest.fixture(scope="session")
def app_module():
    """Import and return the FastAPI app, without running its startup event."""
    from app.main import app

    return app


@pytest.fixture
def memory_db():
    """Session factory for a fresh in-memory SQLite database with the app schema.

    StaticPool keeps one shared connection; without it every connection
    would see its own empty ':memory:' database."""
    from app.database import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def open_client(app_module):
    """Factory for TestClients on a test database.

    `open_client(Session, user_id=1)` points get_db at `Session` and makes
    require_auth / get_current_user return that user (None for
    `user_id=None`). With `override_auth=False` the real authentication
    runs. The client is already entered (startup has run) and carries the
    factory as `client.session_factory`. Clients close and all dependency
    overrides are cleared after the test."""
    from fastapi.testclient import TestClient

    from app.auth import get_current_user, require_auth
    from app.database import User, get_db

    stack = ExitStack()

    def _open(Session, user_id=1, *, override_auth=True):
        def _get_db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        def _user():
            if user_id is None:
                return None
            s = Session()
            try:
                return s.query(User).filter(User.id == user_id).first()
            finally:
                s.close()

        app_module.dependency_overrides[get_db] = _get_db
        if override_auth:
            app_module.dependency_overrides[require_auth] = _user
            app_module.dependency_overrides[get_current_user] = _user
        client = stack.enter_context(TestClient(app_module))
        client.session_factory = Session
        return client

    try:
        yield _open
    finally:
        stack.close()
        app_module.dependency_overrides.clear()


@pytest.fixture
def client(app_module):
    """Synchronous TestClient; entering it runs the startup event."""
    from fastapi.testclient import TestClient

    with TestClient(app_module) as c:
        yield c


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
