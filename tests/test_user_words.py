"""
Phase-A word-state API: round-trip the lifecycle (new → learning → known →
ignored → cleared back to new), bulk-mark, stats, and the join into the
/api/analyze response.

Uses an in-memory SQLite engine + dependency overrides so the tests are
hermetic and do not depend on the deployed data directory.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user, require_auth
from app.database import Base, User, UserWord, get_db


@pytest.fixture
def words_client(app_module, monkeypatch):
    # StaticPool keeps a single shared connection, which is required for
    # SQLite ':memory:' — otherwise every new SQLAlchemy connection sees a
    # fresh empty database and 'no such table: users' fires.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Seed a single user; both auth dependencies return it.
    db = TestingSession()
    test_user = User(
        id=1,
        username="alice",
        password_hash="x",
        is_admin=False,
        must_change_password=False,
        invite_quota=0,
    )
    db.add(test_user)
    db.commit()
    db.close()

    def _override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    def _override_user():
        s = TestingSession()
        try:
            return s.query(User).filter(User.id == 1).first()
        finally:
            s.close()

    app_module.dependency_overrides[get_db] = _override_get_db
    app_module.dependency_overrides[require_auth] = _override_user
    app_module.dependency_overrides[get_current_user] = _override_user
    try:
        with TestClient(app_module) as c:
            # Expose the session factory so package-snapshot tests can
            # peek at UserWord rows directly (the API surfaces state but
            # not the snapshot columns).
            c.session_factory = TestingSession  # type: ignore[attr-defined]
            yield c
    finally:
        app_module.dependency_overrides.clear()


def test_set_state_then_list_roundtrip(words_client):
    r = words_client.post("/api/words/state", json={"word": "你好", "state": "learning"})
    assert r.status_code == 200, r.text
    assert r.json() == {"word": "你好", "state": "learning"}

    r = words_client.get("/api/words/state")
    assert r.status_code == 200
    assert r.json()["states"] == {"你好": "learning"}


def test_promote_to_known_then_ignored(words_client):
    words_client.post("/api/words/state", json={"word": "再见", "state": "learning"})
    words_client.post("/api/words/state", json={"word": "再见", "state": "known"})
    words_client.post("/api/words/state", json={"word": "再见", "state": "ignored"})
    states = words_client.get("/api/words/state").json()["states"]
    assert states == {"再见": "ignored"}


def test_delete_resets_to_new(words_client):
    words_client.post("/api/words/state", json={"word": "谢谢", "state": "known"})
    r = words_client.delete("/api/words/state", params={"word": "谢谢"})
    assert r.status_code == 200
    assert words_client.get("/api/words/state").json()["states"] == {}


def test_invalid_state_rejected(words_client):
    r = words_client.post("/api/words/state", json={"word": "你好", "state": "??"})
    assert r.status_code == 400


def test_bulk_mark_known(words_client):
    r = words_client.post(
        "/api/words/bulk-mark-known",
        json={"words": ["一", "二", "三", "一"], "source_text_id": None},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 3  # dedup: '一' counted once for new inserts
    states = words_client.get("/api/words/state").json()["states"]
    assert states == {"一": "known", "二": "known", "三": "known"}


def test_bulk_mark_promotes_learning_to_known(words_client):
    words_client.post("/api/words/state", json={"word": "苹果", "state": "learning"})
    r = words_client.post("/api/words/bulk-mark-known", json={"words": ["苹果"]})
    assert r.json()["updated"] == 1
    assert words_client.get("/api/words/state").json()["states"] == {"苹果": "known"}


def test_stats_endpoint(words_client):
    words_client.post("/api/words/state", json={"word": "猫", "state": "learning"})
    words_client.post("/api/words/state", json={"word": "狗", "state": "known"})
    words_client.post("/api/words/state", json={"word": "鸟", "state": "ignored"})
    body = words_client.get("/api/words/stats").json()
    assert body["learning"] == 1
    assert body["known"] == 1
    assert body["ignored"] == 1
    # Streak: first-ever activity above started a fresh streak today.
    assert body["streak"] == 1


# --- Phase #100 follow-up: package-curated meaning snapshots ----------------


def _fetch_row(client, word: str) -> UserWord | None:
    """Look the UserWord row up directly — the API surface returns only
    `state`, so snapshot-related assertions need to bypass it. Eager-loads
    glosses so Phase #120 tests can inspect them after the session closes."""
    from sqlalchemy.orm import joinedload

    session = client.session_factory()
    try:
        row = (
            session.query(UserWord)
            .options(joinedload(UserWord.glosses))
            .filter(UserWord.word == word)
            .first()
        )
        if row is not None:
            # Expunge so the caller can read attributes after session
            # close without lazy-loading or DetachedInstanceError.
            session.expunge(row)
        return row
    finally:
        session.close()


def test_set_state_with_package_snapshot_stores_meaning(words_client):
    """Phase #120 — a package click stores the package gloss as a
    separate UserWordGloss row tagged with the package name, in
    addition to whatever dictionary gloss the chain produced. Both
    co-exist on the same UserWord."""
    r = words_client.post(
        "/api/words/state",
        json={
            "word": "道",
            "state": "learning",
            "meaning": "the Dao",
            "pinyin": "dào",
            "translation_source": "package",
            "package_source": "dao_de_jing_ch1",
        },
    )
    assert r.status_code == 200, r.text

    row = _fetch_row(words_client, "道")
    assert row is not None
    # Package gloss is one of the row's glosses, tagged with the package
    # name. The legacy meaning column carries the first gloss (dict or
    # package, whichever landed first).
    pkg_glosses = [g for g in row.glosses if g.source == "package"]
    assert any(g.meaning == "the Dao" for g in pkg_glosses)
    assert any(g.source_tag == "dao_de_jing_ch1" for g in pkg_glosses)


def test_package_and_dictionary_glosses_coexist(words_client):
    """Phase #120 — the dictionary gloss and the package gloss live as
    separate UserWordGloss rows on the same UserWord, so the popover
    and review card can render both with their tags."""
    # First a non-package click — only the dictionary gloss exists.
    words_client.post("/api/words/state", json={"word": "德", "state": "learning"})
    row = _fetch_row(words_client, "德")
    assert row is not None
    initial_glosses = list(row.glosses)
    # Either the dictionary chain found a meaning (one dictionary gloss)
    # or it didn't (no glosses at all in this test env).
    if initial_glosses:
        assert all(g.source == "dictionary" for g in initial_glosses)

    # Second click in a package — the package gloss is *added*, not a
    # replacement. The dictionary gloss (if any) is untouched.
    words_client.post(
        "/api/words/state",
        json={
            "word": "德",
            "state": "learning",
            "meaning": "virtue / Daoist sense",
            "pinyin": "dé",
            "translation_source": "package",
            "package_source": "dao_de_jing_ch1",
        },
    )
    row = _fetch_row(words_client, "德")
    assert row is not None
    pkg = [g for g in row.glosses if g.source == "package"]
    assert any(g.meaning == "virtue / Daoist sense" for g in pkg)


def test_package_snapshot_idempotent_within_same_package(words_client):
    """Phase #120 — repeated clicks on the same word in the same package
    don't pile up duplicate gloss rows. (source, source_tag) acts as
    the unique key for gloss equivalence."""
    payload = {
        "word": "无",
        "state": "learning",
        "meaning": "non-being (Wang Bi)",
        "pinyin": "wú",
        "translation_source": "package",
        "package_source": "dao_de_jing_ch1",
    }
    words_client.post("/api/words/state", json=payload)
    words_client.post("/api/words/state", json=payload)
    row = _fetch_row(words_client, "无")
    assert row is not None
    matching = [
        g
        for g in row.glosses
        if g.source == "package" and g.source_tag == "dao_de_jing_ch1"
    ]
    assert len(matching) == 1


def test_two_packages_produce_two_package_glosses(words_client):
    """Phase #120 — clicking the same word in two *different* packages
    produces two distinct gloss rows so each context's meaning is
    preserved with its tag."""
    words_client.post(
        "/api/words/state",
        json={
            "word": "无",
            "state": "learning",
            "meaning": "non-being (Wang Bi)",
            "pinyin": "wú",
            "translation_source": "package",
            "package_source": "dao_de_jing_ch1",
        },
    )
    words_client.post(
        "/api/words/state",
        json={
            "word": "无",
            "state": "learning",
            "meaning": "without (Mahayana sutra usage)",
            "pinyin": "wú",
            "translation_source": "package",
            "package_source": "heart_sutra",
        },
    )
    row = _fetch_row(words_client, "无")
    assert row is not None
    tags = sorted(g.source_tag for g in row.glosses if g.source == "package")
    assert tags == ["dao_de_jing_ch1", "heart_sutra"]


def test_set_state_without_snapshot_falls_back_to_dictionary(words_client):
    """Non-package callers (the HSK / CC-CEDICT / pypinyin path the
    reader uses for most clicks) must keep today's behaviour: the
    backend resolves via lookup_pinyin_meaning() and never stamps
    'package'."""
    r = words_client.post("/api/words/state", json={"word": "中", "state": "learning"})
    assert r.status_code == 200
    row = _fetch_row(words_client, "中")
    assert row is not None
    assert row.meaning_source != "package"


def test_bulk_mark_known_with_snapshots(words_client):
    """Phase #120 — bulk-mark-known applies the per-word snapshot the
    same way the single-word endpoint does: a package snapshot lands as
    a tagged UserWordGloss row; words without a snapshot only get the
    dictionary gloss."""
    r = words_client.post(
        "/api/words/bulk-mark-known",
        json={
            "words": ["天", "地"],
            "snapshots": {
                "天": {
                    "meaning": "Heaven (cosmological)",
                    "pinyin": "tiān",
                    "translation_source": "package",
                    "package_source": "dao_de_jing_ch1",
                },
            },
        },
    )
    assert r.status_code == 200, r.text

    tian = _fetch_row(words_client, "天")
    assert tian is not None
    pkg = [g for g in tian.glosses if g.source == "package"]
    assert any(
        g.meaning == "Heaven (cosmological)" and g.source_tag == "dao_de_jing_ch1"
        for g in pkg
    )

    di = _fetch_row(words_client, "地")
    assert di is not None
    # No snapshot supplied for 地 → no package gloss should exist on it.
    assert all(g.source != "package" for g in di.glosses)
