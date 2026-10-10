"""
Characterisation tests for GET /api/words/queue (the /words page list).

They pin down the filter, sort and paging behaviour. HSK filter and HSK sort
are applied in SQL, so `total`, `has_more` and every page agree with each
other no matter how many rows the user has.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import state
from app.auth import get_current_user, require_auth
from app.database import Base, User, UserWord, get_db

BASE_TIME = datetime(2026, 1, 1)


def _utcnow():
    # The queue stores and compares naive UTC timestamps.
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def queue_client(app_module):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSession()
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
            # Startup refills state.hsk_vocab, so swap it only after the
            # client has entered, and restore it afterwards.
            saved_vocab = dict(state.hsk_vocab)
            state.hsk_vocab.clear()
            c.session_factory = TestingSession  # type: ignore[attr-defined]
            try:
                yield c
            finally:
                state.hsk_vocab.clear()
                state.hsk_vocab.update(saved_vocab)
    finally:
        app_module.dependency_overrides.clear()


def _add(client, rows):
    """rows: iterable of dicts with at least `word`; other UserWord columns optional."""
    s = client.session_factory()
    for i, row in enumerate(rows):
        data = {
            "user_id": 1,
            "state": "learning",
            "seen_count": 1,
            "created_at": BASE_TIME + timedelta(minutes=i),
            "due_at": None,
        }
        data.update(row)
        s.add(UserWord(**data))
    s.commit()
    s.close()


def _seed_numbered(client, n):
    """n learning words w000..w(n-1), created one minute apart (w000 oldest)."""
    _add(client, [{"word": f"w{i:03d}"} for i in range(n)])


def _get(client, **params):
    r = client.get("/api/words/queue", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _words(body):
    return [it["word"] for it in body["items"]]


# --- basics -------------------------------------------------------------------


def test_empty_queue(queue_client):
    assert _get(queue_client) == {"items": [], "total": 0, "has_more": False}


def test_item_shape_and_hsk_level(queue_client):
    now = _utcnow()
    _add(
        queue_client,
        [
            {
                "word": "你好",
                "pinyin": "nǐ hǎo",
                "meaning": "hello",
                "due_at": now + timedelta(days=2),
                "stability": 3.5,
            }
        ],
    )
    state.hsk_vocab["你好"] = {"level_new": "new-1", "pinyin": "nǐ hǎo", "meaning": "hello"}
    body = _get(queue_client)
    assert body["total"] == 1
    item = body["items"][0]
    assert item["word"] == "你好"
    assert item["state"] == "learning"
    assert item["pinyin"] == "nǐ hǎo"
    assert item["meaning"] == "hello"
    assert item["hsk_level"] == 1
    assert item["stability"] == 3.5
    assert item["due_at"].startswith((now + timedelta(days=2)).date().isoformat())
    assert 0 < item["seconds_until_due"] <= 2 * 86400
    assert item["created_at"] == BASE_TIME.isoformat()
    for key in ("seen_count", "ease", "difficulty", "last_reviewed_at"):
        assert key in item


def test_word_outside_hsk_has_no_level(queue_client):
    _add(queue_client, [{"word": "饕餮"}])
    assert _get(queue_client)["items"][0]["hsk_level"] is None


def test_only_own_rows_are_listed(queue_client):
    s = queue_client.session_factory()
    s.add(User(id=2, username="bob", password_hash="x", invite_quota=0))
    s.commit()
    s.close()
    _add(queue_client, [{"word": "我的"}, {"word": "他的", "user_id": 2}])
    body = _get(queue_client)
    assert _words(body) == ["我的"]
    assert body["total"] == 1


# --- state filter ---------------------------------------------------------------


@pytest.fixture
def mixed_states(queue_client):
    _add(
        queue_client,
        [
            {"word": "学", "state": "learning"},
            {"word": "看", "state": "known"},
            {"word": "啊", "state": "ignored"},
            {"word": "写", "state": "learning"},
        ],
    )
    return queue_client


def test_no_state_filter_returns_all_states(mixed_states):
    body = _get(mixed_states)
    assert sorted(_words(body)) == sorted(["学", "看", "啊", "写"])
    assert body["total"] == 4


def test_state_filter_single(mixed_states):
    body = _get(mixed_states, state="learning")
    assert sorted(_words(body)) == sorted(["学", "写"])
    assert body["total"] == 2


def test_state_filter_comma_separated(mixed_states):
    body = _get(mixed_states, state="known, ignored")
    assert sorted(_words(body)) == sorted(["看", "啊"])
    assert body["total"] == 2


def test_state_filter_rejects_unknown_state(mixed_states):
    r = mixed_states.get("/api/words/queue", params={"state": "learning,new"})
    assert r.status_code == 400


# --- due filter -----------------------------------------------------------------


@pytest.fixture
def due_spread(queue_client):
    now = _utcnow()
    _add(
        queue_client,
        [
            {"word": "过去", "due_at": now - timedelta(days=1)},
            {"word": "未排", "due_at": None},
            {"word": "三天", "due_at": now + timedelta(days=3)},
            {"word": "十天", "due_at": now + timedelta(days=10)},
        ],
    )
    return queue_client


def test_due_within_zero_days_includes_overdue_and_unscheduled(due_spread):
    body = _get(due_spread, due_within_days=0)
    assert sorted(_words(body)) == sorted(["过去", "未排"])
    assert body["total"] == 2


def test_due_within_seven_days(due_spread):
    body = _get(due_spread, due_within_days=7)
    assert sorted(_words(body)) == sorted(["过去", "未排", "三天"])
    assert body["total"] == 3


def test_no_due_filter_returns_everything(due_spread):
    assert _get(due_spread)["total"] == 4


# --- search ---------------------------------------------------------------------


def test_search_is_substring_match(queue_client):
    _add(queue_client, [{"word": "学生"}, {"word": "学习"}, {"word": "大学"}, {"word": "老师"}])
    body = _get(queue_client, search="学")
    assert sorted(_words(body)) == sorted(["学生", "学习", "大学"])
    assert body["total"] == 3
    body = _get(queue_client, search=" 学生 ")
    assert _words(body) == ["学生"]
    assert body["total"] == 1


def test_search_combines_with_state(queue_client):
    _add(
        queue_client,
        [
            {"word": "学生", "state": "known"},
            {"word": "学习", "state": "learning"},
            {"word": "老师", "state": "learning"},
        ],
    )
    body = _get(queue_client, search="学", state="learning")
    assert _words(body) == ["学习"]
    assert body["total"] == 1


# --- sorting --------------------------------------------------------------------


def test_sort_recent_is_newest_first(queue_client):
    _seed_numbered(queue_client, 5)
    assert _words(_get(queue_client, sort="recent")) == ["w004", "w003", "w002", "w001", "w000"]


def test_sort_due_is_soonest_first_with_unscheduled_last(queue_client):
    now = _utcnow()
    _add(
        queue_client,
        [
            {"word": "无期", "due_at": None},
            {"word": "后天", "due_at": now + timedelta(days=2)},
            {"word": "昨天", "due_at": now - timedelta(days=1)},
            {"word": "明天", "due_at": now + timedelta(days=1)},
        ],
    )
    expected = ["昨天", "明天", "后天", "无期"]
    assert _words(_get(queue_client, sort="due")) == expected
    # 'due' is also the default.
    assert _words(_get(queue_client)) == expected


def test_sort_hsk_orders_page_by_level(queue_client):
    _add(queue_client, [{"word": "难"}, {"word": "易"}, {"word": "外"}, {"word": "中"}])
    state.hsk_vocab.update(
        {
            "难": {"level_new": "new-5"},
            "易": {"level_new": "new-1"},
            "中": {"level_new": "new-3"},
        }
    )
    body = _get(queue_client, sort="hsk")
    assert _words(body) == ["易", "中", "难", "外"]
    assert [it["hsk_level"] for it in body["items"]] == [1, 3, 5, None]


# --- paging ---------------------------------------------------------------------


def test_limit_offset_pages_are_disjoint_and_complete(queue_client):
    _seed_numbered(queue_client, 25)
    seen = []
    for offset in (0, 10, 20):
        body = _get(queue_client, sort="recent", limit=10, offset=offset)
        assert body["total"] == 25
        seen.extend(_words(body))
    assert len(seen) == 25
    assert seen == [f"w{i:03d}" for i in range(24, -1, -1)]


def test_total_ignores_limit(queue_client):
    _seed_numbered(queue_client, 12)
    body = _get(queue_client, limit=5)
    assert len(body["items"]) == 5
    assert body["total"] == 12


def test_offset_past_end_returns_empty_page(queue_client):
    _seed_numbered(queue_client, 3)
    body = _get(queue_client, offset=10)
    assert body["items"] == []
    assert body["total"] == 3


def test_negative_offset_is_treated_as_zero(queue_client):
    _seed_numbered(queue_client, 3)
    body = _get(queue_client, sort="recent", offset=-5)
    assert _words(body) == ["w002", "w001", "w000"]


def test_default_limit_is_200(queue_client):
    _seed_numbered(queue_client, 210)
    body = _get(queue_client)
    assert len(body["items"]) == 200
    assert body["total"] == 210


def test_limit_is_capped_at_500(queue_client):
    _seed_numbered(queue_client, 510)
    body = _get(queue_client, limit=10_000)
    assert len(body["items"]) == 500
    assert body["total"] == 510


# --- HSK filter -----------------------------------------------------------------


def test_hsk_filter_within_a_single_page(queue_client):
    _add(queue_client, [{"word": "一"}, {"word": "二"}, {"word": "三"}, {"word": "外"}])
    state.hsk_vocab.update(
        {
            "一": {"level_new": "new-1"},
            "二": {"level_new": "new-2"},
            "三": {"level_new": "new-3"},
        }
    )
    assert sorted(_words(_get(queue_client, hsk_levels="1,3"))) == sorted(["一", "三"])
    assert _words(_get(queue_client, hsk_levels="2")) == ["二"]


def test_hsk_filter_rejects_non_integer_levels(queue_client):
    _seed_numbered(queue_client, 1)
    r = queue_client.get("/api/words/queue", params={"hsk_levels": "1,x"})
    assert r.status_code == 400


def _seed_newest_hundred_hsk1(client):
    """300 words; only the newest 100 (w200..w299) are HSK 1."""
    _seed_numbered(client, 300)
    state.hsk_vocab.update({f"w{i:03d}": {"level_new": "new-1"} for i in range(200, 300)})


def test_hsk_filter_across_pages_returns_every_match_and_correct_total(queue_client):
    _seed_newest_hundred_hsk1(queue_client)
    found = []
    for offset in range(0, 300, 50):
        body = _get(queue_client, hsk_levels="1", sort="due", limit=50, offset=offset)
        assert body["total"] == 100
        found.extend(_words(body))
    assert sorted(found) == [f"w{i:03d}" for i in range(200, 300)]


def test_sort_hsk_puts_lowest_levels_on_first_page(queue_client):
    _seed_newest_hundred_hsk1(queue_client)
    body = _get(queue_client, sort="hsk", limit=100)
    assert [it["hsk_level"] for it in body["items"]] == [1] * 100


def test_negative_limit_is_clamped(queue_client):
    _seed_numbered(queue_client, 5)
    body = _get(queue_client, limit=-1)
    assert len(body["items"]) == 1
    assert body["total"] == 5


def test_zero_limit_is_clamped_to_one(queue_client):
    _seed_numbered(queue_client, 3)
    body = _get(queue_client, limit=0)
    assert len(body["items"]) == 1
    assert body["has_more"] is True


# --- has_more -------------------------------------------------------------------


def test_has_more_tracks_the_last_page(queue_client):
    _seed_numbered(queue_client, 25)
    assert _get(queue_client, limit=10, offset=0)["has_more"] is True
    assert _get(queue_client, limit=10, offset=10)["has_more"] is True
    assert _get(queue_client, limit=10, offset=20)["has_more"] is False
    assert _get(queue_client, limit=25)["has_more"] is False
    assert _get(queue_client, limit=10, offset=40)["has_more"] is False


def test_has_more_with_hsk_filter(queue_client):
    _seed_newest_hundred_hsk1(queue_client)
    body = _get(queue_client, hsk_levels="1", limit=60)
    assert len(body["items"]) == 60
    assert body["has_more"] is True
    body = _get(queue_client, hsk_levels="1", limit=60, offset=60)
    assert len(body["items"]) == 40
    assert body["has_more"] is False


# --- HSK filter + sort across pages ----------------------------------------------


def test_sort_hsk_across_pages_is_globally_ordered(queue_client):
    # 300 words; levels cycle 6,5,...,1,None in insertion order, so only a
    # sort over the full set (not per page) yields a monotonic sequence.
    _seed_numbered(queue_client, 300)
    cycle = [6, 5, 4, 3, 2, 1, None]
    for i in range(300):
        lvl = cycle[i % len(cycle)]
        if lvl is not None:
            state.hsk_vocab[f"w{i:03d}"] = {"level_new": f"new-{lvl}"}
    levels, words = [], []
    for offset in range(0, 300, 40):
        body = _get(queue_client, sort="hsk", limit=40, offset=offset)
        assert body["total"] == 300
        levels.extend(it["hsk_level"] for it in body["items"])
        words.extend(_words(body))
    assert len(words) == 300 == len(set(words))
    known = [lv for lv in levels if lv is not None]
    assert known == sorted(known)
    # Words outside HSK come last.
    assert levels[len(known) :] == [None] * (300 - len(known))
    # Within a level, oldest first.
    lvl1 = [w for w, lv in zip(words, levels, strict=True) if lv == 1]
    assert lvl1 == sorted(lvl1)


def test_hsk_filter_and_sort_hsk_combine(queue_client):
    _add(queue_client, [{"word": "难"}, {"word": "易"}, {"word": "外"}, {"word": "中"}])
    state.hsk_vocab.update(
        {
            "难": {"level_new": "new-5"},
            "易": {"level_new": "new-1"},
            "中": {"level_new": "new-3"},
        }
    )
    body = _get(queue_client, sort="hsk", hsk_levels="5,1")
    assert _words(body) == ["易", "难"]
    assert body["total"] == 2


def test_hsk_filter_combines_with_state_and_search(queue_client):
    _add(
        queue_client,
        [
            {"word": "学生", "state": "known"},
            {"word": "学习", "state": "learning"},
            {"word": "学者", "state": "learning"},
            {"word": "老师", "state": "learning"},
        ],
    )
    state.hsk_vocab.update(
        {
            "学生": {"level_new": "new-1"},
            "学习": {"level_new": "new-1"},
            "学者": {"level_new": "new-6"},
            "老师": {"level_new": "new-1"},
        }
    )
    body = _get(queue_client, hsk_levels="1", state="learning", search="学")
    assert _words(body) == ["学习"]
    assert body["total"] == 1


def test_hsk_filter_and_sort_with_full_size_vocab(queue_client):
    # A realistic ~13k-word vocab must not trip SQLite's bound-parameter limit.
    state.hsk_vocab.update({f"v{i:05d}": {"level_new": f"new-{i % 7 + 1}"} for i in range(13_000)})
    _add(queue_client, [{"word": f"v{i:05d}"} for i in range(700)])
    body = _get(queue_client, hsk_levels="1,2,3,4,5,6,7", limit=500)
    assert body["total"] == 700
    assert len(body["items"]) == 500
    body = _get(queue_client, hsk_levels="1", limit=500)
    assert body["total"] == 100
    assert {it["hsk_level"] for it in body["items"]} == {1}
    body = _get(queue_client, sort="hsk", limit=500, offset=500)
    page_levels = [it["hsk_level"] for it in body["items"]]
    assert len(page_levels) == 200
    assert page_levels == sorted(page_levels)
    assert page_levels[0] >= 5
