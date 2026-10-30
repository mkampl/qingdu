"""Glue-word migration (app/services/glue_migration.py).

User words such as 很多 or 洗衣服 are split into their dictionary parts:
parts the user already has stay untouched, missing parts copy the glued
row's state and schedule, the glued row goes (its events stay).
"""

import json
import sqlite3
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import (
    Base,
    User,
    UserWord,
    UserWordEvent,
    UserWordGloss,
    VocabularyList,
)
from app.services import dict_data, glue_migration

DUE = datetime(2026, 11, 1, 8, 0, 0)
REVIEWED = datetime(2026, 10, 1, 8, 0, 0)


@pytest.fixture
def small_dicts(swap_dictionaries):
    swap_dictionaries(
        hsk={
            w: {"pinyin": py, "meaning": m, "is_original_hsk": True}
            for w, py, m in [
                ("很", "hěn", "very"),
                ("多", "duō", "many"),
                ("洗", "xǐ", "to wash"),
                ("衣服", "yī fu", "clothes"),
                ("我", "wǒ", "I"),
                ("来", "lái", "to come"),
            ]
        },
        cedict={"大卫": {"pinyin": "dà wèi", "meaning": "David"}},
    )


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "qingdu.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add_all(
        [
            User(id=1, username="alice", password_hash="x"),
            User(id=2, username="bob", password_hash="x"),
        ]
    )
    glued = UserWord(
        user_id=1,
        word="洗衣服",
        state="learning",
        seen_count=4,
        stability=3.5,
        difficulty=5.2,
        fsrs_state='{"state": 2}',
        due_at=DUE,
        last_reviewed_at=REVIEWED,
        meaning="to wash + clothes",
    )
    session.add_all(
        [
            glued,
            UserWord(user_id=1, word="洗", state="known", stability=120.0, meaning="to wash"),
            UserWord(user_id=1, word="很多", state="known", stability=90.0),
            UserWord(user_id=1, word="大卫", state="learning"),
            UserWord(user_id=1, word="我来", state="known", meaning_source="package"),
            UserWord(user_id=1, word="洗多", state="learning"),
            UserWord(user_id=2, word="很多", state="learning", stability=1.0),
            UserWord(user_id=2, word="很", state="ignored"),
            UserWord(user_id=2, word="来多", state="known"),
            VocabularyList(
                user_id=2,
                name="mine",
                list_type="custom",
                sections=json.dumps([{"words": [{"hanzi": "来多"}]}]),
            ),
            UserWordEvent(user_id=1, word="洗衣服", event_type="state_change"),
        ]
    )
    session.flush()
    session.add(
        UserWordGloss(user_word_id=glued.id, meaning="to wash + clothes", source="dictionary")
    )
    session.commit()
    session.close()
    engine.dispose()
    return path


def _rows(path, user_id):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return {
            r["word"]: dict(r)
            for r in conn.execute("SELECT * FROM user_words WHERE user_id = ?", (user_id,))
        }
    finally:
        conn.close()


def _run(path, *, do_apply):
    conn = sqlite3.connect(path)
    try:
        plans = glue_migration.plan(conn)
        if do_apply:
            glue_migration.apply(conn, plans)
        return plans
    finally:
        conn.close()


def test_plan_lists_glued_rows_per_user(db_path, small_dicts):
    plans = _run(db_path, do_apply=False)
    got = {(p.username, p.word): [(x.word, x.action, x.state) for x in p.parts] for p in plans}
    assert got == {
        ("alice", "洗衣服"): [("洗", "exists", "known"), ("衣服", "create", "learning")],
        ("alice", "很多"): [("很", "create", "known"), ("多", "create", "known")],
        # 多 is created for 很多 (earlier row); 洗多 leaves it to that copy.
        ("alice", "洗多"): [
            ("洗", "exists", "known"),
            ("多", "exists", "known"),
        ],
        ("bob", "很多"): [("很", "exists", "ignored"), ("多", "create", "learning")],
    }
    shared = next(p for p in plans if p.word == "洗多").parts[1]
    assert shared.created_for == "很多"
    # Dry run changes nothing.
    assert "洗衣服" in _rows(db_path, 1)


def test_apply_splits_rows_and_keeps_existing_parts(db_path, small_dicts):
    before = _rows(db_path, 1)
    _run(db_path, do_apply=True)
    alice = _rows(db_path, 1)

    assert "洗衣服" not in alice and "很多" not in alice and "洗多" not in alice
    # Existing part untouched.
    assert alice["洗"] == before["洗"]
    # Missing part copies the glued row's state and schedule.
    new = alice["衣服"]
    assert new["state"] == "learning"
    assert new["stability"] == 3.5 and new["difficulty"] == 5.2
    assert new["fsrs_state"] == '{"state": 2}'
    assert new["seen_count"] == 4
    assert new["due_at"].startswith("2026-11-01 08:00:00")
    assert new["last_reviewed_at"].startswith("2026-10-01 08:00:00")
    assert (new["pinyin"], new["meaning"], new["meaning_source"]) == (
        "yī fu",
        "clothes",
        "dictionary",
    )
    assert alice["很"]["state"] == "known" and alice["多"]["stability"] == 90.0
    # Dictionary, package and list words are not glued.
    assert {"大卫", "我来"} <= set(alice)

    bob = _rows(db_path, 2)
    assert bob["很"]["state"] == "ignored"
    assert bob["多"]["state"] == "learning"
    assert "来多" in bob and "很多" not in bob

    conn = sqlite3.connect(db_path)
    try:
        glosses = conn.execute(
            "SELECT g.meaning FROM user_word_glosses g"
            " LEFT JOIN user_words w ON w.id = g.user_word_id"
            " WHERE w.id IS NULL OR g.meaning LIKE '% + %'"
        ).fetchall()
        assert glosses == []
        new_gloss = conn.execute(
            "SELECT g.source, g.meaning FROM user_word_glosses g"
            " JOIN user_words w ON w.id = g.user_word_id WHERE w.user_id = 1 AND w.word = '衣服'"
        ).fetchall()
        assert new_gloss == [("dictionary", "clothes")]
        events = conn.execute(
            "SELECT count(*) FROM user_word_events WHERE word = '洗衣服'"
        ).fetchone()[0]
        assert events == 1
    finally:
        conn.close()


def test_second_run_finds_nothing(db_path, small_dicts):
    _run(db_path, do_apply=True)
    after_first = _rows(db_path, 1), _rows(db_path, 2)
    assert _run(db_path, do_apply=True) == []
    assert (_rows(db_path, 1), _rows(db_path, 2)) == after_first


def test_refuses_without_dictionaries(db_path, swap_dictionaries):
    swap_dictionaries(cedict={})
    with pytest.raises(RuntimeError):
        _run(db_path, do_apply=False)


def test_cli_dry_run_and_json(db_path, small_dicts, monkeypatch, capsys):
    monkeypatch.setattr(dict_data, "load_pinned_dictionaries", lambda: None)
    assert glue_migration.main(["--db", str(db_path)]) == 0
    out = capsys.readouterr().out
    assert "洗衣服" in out and "衣服 (create: learning)" in out
    assert "4 glued rows -> delete" in out
    assert "洗衣服" in _rows(db_path, 1)

    assert glue_migration.main(["--db", str(db_path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {d["word"] for d in data} == {"洗衣服", "很多", "洗多"}

    assert glue_migration.main(["--db", str(db_path), "--apply"]) == 0
    capsys.readouterr()
    assert "洗衣服" not in _rows(db_path, 1)
    assert glue_migration.main(["--db", str(db_path)]) == 0
    assert "No glued user words found." in capsys.readouterr().out
