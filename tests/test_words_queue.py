"""
Characterisation tests for GET /api/words/queue (the /words page list).

They pin down today's filter, sort and paging behaviour so the paging and
filter rework can't silently change it. Known-wrong behaviour (HSK filter
applied after LIMIT/OFFSET, unclamped negative limit) is recorded as strict
xfail tests that describe the intended result.
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
    assert _get(queue_client) == {"items": [], "total": 0}


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


@pytest.mark.xfail(
    strict=True,
    reason="HSK filter runs after LIMIT/OFFSET, so pages miss matches and total counts all rows",
)
def test_hsk_filter_across_pages_returns_every_match_and_correct_total(queue_client):
    _seed_newest_hundred_hsk1(queue_client)
    found = []
    for offset in range(0, 300, 50):
        body = _get(queue_client, hsk_levels="1", sort="due", limit=50, offset=offset)
        assert body["total"] == 100
        found.extend(_words(body))
    assert sorted(found) == [f"w{i:03d}" for i in range(200, 300)]


@pytest.mark.xfail(
    strict=True,
    reason="sort=hsk only re-sorts the current page; lowest levels don't come first overall",
)
def test_sort_hsk_puts_lowest_levels_on_first_page(queue_client):
    _seed_newest_hundred_hsk1(queue_client)
    body = _get(queue_client, sort="hsk", limit=100)
    assert [it["hsk_level"] for it in body["items"]] == [1] * 100


@pytest.mark.xfail(strict=True, reason="negative limit is passed to SQL as LIMIT -1 (no limit)")
def test_negative_limit_is_clamped(queue_client):
    _seed_numbered(queue_client, 5)
    body = _get(queue_client, limit=-1)
    assert len(body["items"]) == 1
    assert body["total"] == 5
