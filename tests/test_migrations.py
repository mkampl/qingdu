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
    assert {
        "invite_quota",
        "streak_count",
        "review_window",
        "timezone",
        "account_status",
        "token_version",
        "ui_settings",
    } <= cols
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


def test_init_db_backfills_token_version_for_existing_users(db_file):
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
        conn.execute(text("INSERT INTO users (id, username, password_hash) VALUES (1, 'a', 'x')"))
    init_db()
    init_db()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT token_version FROM users WHERE id = 1")).scalar() == 0


def test_init_db_adds_word_count_to_user_word_events(db_file):
    from sqlalchemy import text

    from app.database import init_db

    engine = db_file()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE user_word_events (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "word VARCHAR(64) NOT NULL, event_type VARCHAR(32) NOT NULL, "
                "new_state VARCHAR(16), created_at DATETIME)"
            )
        )
    init_db()
    init_db()
    assert {"grade", "mode", "word_count"} <= _columns(engine, "user_word_events")


def test_init_db_adds_timezone_as_null_for_existing_users(db_file):
    """Existing accounts get no zone (= UTC days) until their browser sends one."""
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
        conn.execute(text("INSERT INTO users (id, username, password_hash) VALUES (1, 'a', 'x')"))
    init_db()
    init_db()
    assert "timezone" in _columns(engine, "users")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT timezone FROM users WHERE id = 1")).scalar() is None


def test_init_db_adds_dict_version_to_vocabulary_lists(db_file):
    from sqlalchemy import text

    from app.database import init_db

    engine = db_file()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE vocabulary_lists (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "name VARCHAR(255), list_type VARCHAR(50), sections TEXT, anki_deck_id INTEGER, "
                "created_at DATETIME)"
            )
        )
        conn.execute(
            text("INSERT INTO vocabulary_lists (id, user_id, sections) VALUES (1, 1, '[]')")
        )
    init_db()
    init_db()
    assert {"apply_as_glossary", "dict_version"} <= _columns(engine, "vocabulary_lists")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT dict_version FROM vocabulary_lists")).scalar() is None


def test_init_db_adds_sample_source_to_user_words(db_file):
    from sqlalchemy import text

    from app.database import init_db

    engine = db_file()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE user_words (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "word VARCHAR(64), state VARCHAR(16), sample_sentence TEXT)"
            )
        )
        conn.execute(text("INSERT INTO user_words (id, user_id, word) VALUES (1, 1, '中文')"))
    init_db()
    init_db()
    assert "sample_source" in _columns(engine, "user_words")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT sample_source FROM user_words")).scalar() is None


def test_init_db_adds_review_focus_to_users(db_file):
    from sqlalchemy import text

    from app.database import init_db

    engine = db_file()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64), "
                "password_hash TEXT)"
            )
        )
        conn.execute(text("INSERT INTO users (id, username, password_hash) VALUES (1, 'a', 'x')"))
    init_db()
    init_db()
    assert "review_focus" in _columns(engine, "users")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT review_focus FROM users")).scalar() == "both"


def test_init_db_adds_folder_columns_to_saved_texts(db_file):
    from sqlalchemy import text

    from app.database import init_db

    engine = db_file()
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE saved_texts (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                "title VARCHAR(500), content TEXT, tags TEXT, reading_progress INTEGER, "
                "analysis_data TEXT, created_at DATETIME, share_token VARCHAR(36), "
                "glossary_list_ids TEXT)"
            )
        )
    init_db()
    assert {"folder_id", "position"} <= _columns(engine, "saved_texts")
    assert "parent_id" in _columns(engine, "text_folders")
    init_db()
