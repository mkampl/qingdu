"""Tests for migrate_word_data idempotency and basic shape preservation,
plus the init_db startup schema migrations."""

import pytest

from app.services.migrations import migrate_word_data


def test_idempotent_when_already_migrated():
    word = {"text": "你好", "level_new": "new-1", "hsk_level": "new-1"}
    assert migrate_word_data(dict(word)) == word


def test_returns_input_when_no_level():
    word = {"text": "?"}
    assert migrate_word_data(dict(word)) == word


def test_legacy_new_level_assigns_level_new():
    word = {"text": "?somethingnotinhsk?", "hsk_level": "new-3"}
    out = migrate_word_data(word)
    assert out["level_new"] == "new-3"
    assert out["level_old"] is None


def test_legacy_old_level_assigns_level_old():
    word = {"text": "?somethingnotinhsk?", "hsk_level": "old-2"}
    out = migrate_word_data(word)
    assert out["level_old"] == "old-2"
    assert out["level_new"] is None


# ---- init_db schema migrations ----------------------------------------


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    """Point app.database at a throwaway SQLite file; returns a helper
    that swaps in an engine for it (optionally read-only)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import database

    path = tmp_path / "qingdu.db"

    def use(read_only: bool = False):
        url = f"sqlite:///file:{path}?mode=ro&uri=true" if read_only else f"sqlite:///{path}"
        engine = create_engine(url, connect_args={"check_same_thread": False})
        monkeypatch.setattr(database, "engine", engine)
        monkeypatch.setattr(
            database, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine)
        )
        return engine

    return use


def _columns(engine, table):
    from sqlalchemy import inspect

    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_init_db_is_idempotent(db_file):
    from app.database import init_db

    engine = db_file()
    init_db()
    init_db()
    assert "account_status" in _columns(engine, "users")


def test_init_db_adds_missing_columns_to_legacy_table(db_file):
    from sqlalchemy import text

    from app.database import init_db

    engine = db_file()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50) UNIQUE "
                "NOT NULL, password_hash VARCHAR(255) NOT NULL, is_admin BOOLEAN, "
                "must_change_password BOOLEAN, last_active DATETIME, created_at DATETIME)"
            )
        )
    init_db()
    cols = _columns(engine, "users")
    assert {"invite_quota", "streak_count", "review_window", "account_status"} <= cols
    init_db()  # second boot: every column exists, nothing to do


def test_init_db_raises_when_a_migration_fails(db_file):
    """A failed ALTER must stop the boot instead of leaving the app running
    on a half-migrated schema."""
    from sqlalchemy import text

    from app.database import Base, init_db

    engine = db_file()
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users DROP COLUMN account_status"))
    engine.dispose()

    db_file(read_only=True)  # the ALTER that re-adds the column will fail
    with pytest.raises(Exception, match="readonly"):
        init_db()
