"""Pytest fixtures shared across the test suite."""

import os
from contextlib import ExitStack
from datetime import datetime, timedelta

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
def alice_db(memory_db):
    """`memory_db` with one plain user, alice (id 1)."""
    from app.database import User

    db = memory_db()
    db.add(
        User(
            id=1,
            username="alice",
            password_hash="x",
            is_admin=False,
            must_change_password=False,
            invite_quota=0,
        )
    )
    db.commit()
    db.close()
    return memory_db


@pytest.fixture
def words_client(alice_db, open_client):
    """TestClient signed in as alice; `words_client.session_factory` opens the database."""
    return open_client(alice_db)


@pytest.fixture
def ext_client(alice_db, open_client):
    """TestClient on alice's database with real authentication (JWTs and access tokens)."""
    return open_client(alice_db, override_auth=False)


@pytest.fixture
def review_client(alice_db, open_client):
    """(client, Session) signed in as alice, with review cards in several states."""
    from app.database import UserWord

    # Two due cards (no due_at means brand-new in queue), one already due
    # in the past, one due far in the future (not in the queue), one
    # ignored (not in the queue). A known card due in the past is in the
    # queue too: 'known' is a high-stability SRS state.
    db = alice_db()
    now = datetime.utcnow()
    db.add(UserWord(user_id=1, word="一", state="learning"))
    db.add(UserWord(user_id=1, word="二", state="learning", due_at=now - timedelta(hours=2)))
    db.add(UserWord(user_id=1, word="三", state="learning", due_at=now + timedelta(days=30)))
    db.add(UserWord(user_id=1, word="忽略", state="ignored"))
    db.add(
        UserWord(
            user_id=1,
            word="远期",
            state="known",
            stability=180,
            due_at=now + timedelta(days=120),
        )
    )
    db.commit()
    db.close()
    return open_client(alice_db), alice_db


@pytest.fixture
def fake_llm(monkeypatch):
    """A mocked OpenAI-compatible LLM; append to the yielded list to set its next replies."""
    import asyncio

    import httpx

    from app.services import grammar_ai, llm

    replies: list[str] = []
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        content = replies.pop(0) if replies else '{"ok": true}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "m")
    llm.reset()
    asyncio.run(llm.probe())
    grammar_ai._explained.clear()
    yield replies
    llm.reset()


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
