"""
Local-day boundaries: "today" rolls over at the user's local
midnight for due today, reviewed today, streaks, the daily auto-enrol
batch and the weekly sparkline. Storage stays naive UTC.

Every test pins the clock (`localday.utcnow`) to instants just either side
of a local midnight, in zones on both sides of UTC.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.database import User, UserWord, UserWordEvent
from app.services import enrollment, localday
from app.services.due import end_of_day
from app.services.streak import current_streak, rebase_for_timezone, record_activity

ZONES = ["UTC", "Europe/Vienna", "Asia/Shanghai", "America/Los_Angeles"]
DAY = date(2026, 10, 10)


def at(tz: str, day: date, hh: int, mm: int = 0) -> datetime:
    """Naive UTC for local wall time `day hh:mm` in `tz`."""
    local = datetime(day.year, day.month, day.day, hh, mm, tzinfo=ZoneInfo(tz))
    return local.astimezone(UTC).replace(tzinfo=None)


@pytest.fixture
def clock(monkeypatch):
    """Set the server's "now" (naive UTC) for services and routers alike."""
    state = {"now": datetime(2026, 10, 10, 12, 0)}
    monkeypatch.setattr(localday, "utcnow", lambda: state["now"])

    def set_now(value: datetime) -> None:
        state["now"] = value

    return set_now


@pytest.fixture
def make_session(memory_db):
    return memory_db


def _add_user(Session, tz: str | None, **extra) -> None:
    db = Session()
    db.add(
        User(
            id=1,
            username="alice",
            password_hash="x",
            is_admin=False,
            must_change_password=False,
            invite_quota=0,
            timezone=tz,
            **extra,
        )
    )
    db.commit()
    db.close()


def _add(Session, *rows) -> None:
    db = Session()
    db.add_all(rows)
    db.commit()
    db.close()


def _user(Session) -> User:
    db = Session()
    try:
        return db.query(User).filter(User.id == 1).first()
    finally:
        db.close()


@pytest.fixture
def api(make_session, open_client):
    return open_client(make_session), make_session


# ---- localday helpers ------------------------------------------------------


@pytest.mark.parametrize("tz", ZONES)
def test_day_start_round_trips_to_local_midnight(tz):
    start = localday.day_start_utc(DAY, ZoneInfo(tz))
    assert start == at(tz, DAY, 0)
    assert localday.local_date(start, ZoneInfo(tz)) == DAY
    assert localday.local_date(start - timedelta(seconds=1), ZoneInfo(tz)) == DAY - timedelta(1)


@pytest.mark.parametrize(
    ("tz", "day", "hours"),
    [
        ("Europe/Vienna", date(2026, 3, 29), 23),  # spring forward
        ("Europe/Vienna", date(2026, 10, 25), 25),  # fall back
        ("America/Los_Angeles", date(2026, 3, 8), 23),
        ("America/Los_Angeles", date(2026, 11, 1), 25),
    ],
)
def test_dst_days_have_their_real_length(tz, day, hours):
    zone = ZoneInfo(tz)
    length = localday.day_start_utc(day + timedelta(1), zone) - localday.day_start_utc(day, zone)
    assert length == timedelta(hours=hours)


@pytest.mark.parametrize("name", [None, "", "Mars/Olympus_Mons", "../etc/passwd"])
def test_unknown_or_missing_timezone_means_utc(name):
    assert localday.resolve_tz(name) == localday.UTC_ZONE
    assert not localday.is_valid_timezone(name)


def test_end_of_day_without_tz_is_utc_midnight():
    now = datetime(2026, 10, 10, 23, 59)
    assert end_of_day(now) == datetime(2026, 10, 11)
    assert end_of_day(now, 1) == datetime(2026, 10, 12)


# ---- due today -------------------------------------------------------------


@pytest.mark.parametrize("tz", ZONES)
def test_due_today_ends_at_local_midnight(api, clock, tz):
    client, Session = api
    _add_user(Session, tz)
    _add(
        Session,
        UserWord(user_id=1, word="今", state="learning", due_at=at(tz, DAY, 23, 50)),
        UserWord(user_id=1, word="明", state="learning", due_at=at(tz, DAY + timedelta(1), 0, 10)),
    )
    clock(at(tz, DAY, 23, 30))
    stats = client.get("/api/review/stats").json()
    assert stats["due_today"] == 1
    assert stats["due_in_window"] == 1  # review_window 'today'
    listed = client.get("/api/words/queue", params={"due_within_days": 0}).json()
    assert [w["word"] for w in listed["items"]] == ["今"]
    queue = client.get("/api/review/queue").json()
    assert [c["word"] for c in queue["cards"]] == ["今"]

    # Just past local midnight the next card belongs to the new "today".
    clock(at(tz, DAY + timedelta(1), 0, 5))
    assert client.get("/api/review/stats").json()["due_today"] == 2


# ---- reviewed today --------------------------------------------------------


@pytest.mark.parametrize("tz", ZONES)
def test_reviewed_today_counts_from_local_midnight(api, clock, tz):
    client, Session = api
    _add_user(Session, tz)
    _add(
        Session,
        UserWordEvent(
            user_id=1,
            word="昨",
            event_type="review",
            grade=3,
            created_at=at(tz, DAY - timedelta(1), 23, 50),
        ),
        UserWordEvent(
            user_id=1, word="今", event_type="review", grade=3, created_at=at(tz, DAY, 0, 10)
        ),
    )
    clock(at(tz, DAY, 0, 30))
    assert client.get("/api/review/stats").json()["reviewed_today"] == 1


# ---- streak ----------------------------------------------------------------


@pytest.mark.parametrize("tz", ZONES)
def test_streak_follows_local_days(make_session, tz):
    _add_user(make_session, tz)
    db = make_session()
    user = db.query(User).first()

    record_activity(user, db, now=at(tz, DAY, 23, 30))
    # One hour later, but a new local day: the streak continues.
    record_activity(user, db, now=at(tz, DAY + timedelta(1), 0, 30))
    db.commit()
    assert (user.streak_count, user.streak_last_active) == (2, DAY + timedelta(1))

    # Later the same local day: idempotent.
    record_activity(user, db, now=at(tz, DAY + timedelta(1), 23, 30))
    assert user.streak_count == 2

    # Visible through the whole next local day, gone the day after.
    assert current_streak(user, now=at(tz, DAY + timedelta(2), 23, 59)) == 2
    assert current_streak(user, now=at(tz, DAY + timedelta(3), 0, 1)) == 0

    # A skipped local day with no freezes banked breaks it.
    record_activity(user, db, now=at(tz, DAY + timedelta(3), 0, 30))
    assert user.streak_count == 1


@pytest.mark.parametrize("tz", ZONES)
def test_streak_freeze_bridges_one_local_day(make_session, tz):
    _add_user(
        make_session,
        tz,
        streak_count=9,
        streak_freeze_count=1,
        streak_last_active=DAY - timedelta(2),
    )
    db = make_session()
    user = db.query(User).first()
    assert current_streak(user, now=at(tz, DAY, 0, 1)) == 9
    record_activity(user, db, now=at(tz, DAY, 0, 1))
    assert (user.streak_count, user.streak_freeze_count) == (10, 0)


@pytest.mark.parametrize("new_tz", ZONES)
@pytest.mark.parametrize("utc_hour", range(24))
@pytest.mark.parametrize("last_offset", [0, 1])
def test_switching_timezone_never_breaks_a_live_streak(make_session, new_tz, utc_hour, last_offset):
    """A streak alive under UTC days stays alive after the first timezone
    is set, at any hour of the switch, and the next local day continues it."""
    now = datetime(2026, 10, 10, utc_hour, 30)
    _add_user(
        make_session,
        None,
        streak_count=5,
        streak_freeze_count=0,
        streak_last_active=now.date() - timedelta(days=last_offset),
    )
    db = make_session()
    user = db.query(User).first()
    assert current_streak(user, now=now) == 5

    rebase_for_timezone(user, None, ZoneInfo(new_tz), now=now)
    user.timezone = new_tz
    db.commit()

    assert current_streak(user, now=now) == 5
    record_activity(user, db, now=now)
    assert user.streak_count in (5, 6)
    # And the following local day keeps it going.
    tomorrow = localday.local_date(now, ZoneInfo(new_tz)) + timedelta(1)
    record_activity(user, db, now=at(new_tz, tomorrow, 12))
    assert user.streak_count in (6, 7)


def test_active_yesterday_utc_keeps_streak_after_setting_shanghai(api, clock):
    client, Session = api
    # 20:00 UTC on Oct 10 is already 04:00 Oct 11 in Shanghai. Without the
    # rebase, Oct 9 would be two Shanghai days back and the streak would die.
    clock(datetime(2026, 10, 10, 20, 0))
    _add_user(Session, None, streak_count=5, streak_last_active=date(2026, 10, 9))
    assert client.get("/api/words/stats").json()["streak"] == 5

    r = client.patch("/api/auth/me/settings", json={"timezone": "Asia/Shanghai"})
    assert r.status_code == 200, r.text
    assert r.json()["timezone"] == "Asia/Shanghai"
    assert client.get("/api/words/stats").json()["streak"] == 5
    assert _user(Session).streak_last_active == date(2026, 10, 10)

    # Sending the same zone again (every app start does) moves nothing.
    client.patch("/api/auth/me/settings", json={"timezone": "Asia/Shanghai"})
    assert _user(Session).streak_last_active == date(2026, 10, 10)

    # Acting on the Shanghai day continues it.
    _add(Session, UserWord(user_id=1, word="好", state="learning"))
    client.post("/api/review/grade", json={"word": "好", "grade": 3, "mode": "recognition"})
    assert _user(Session).streak_count == 6


def test_switching_west_does_not_put_last_active_in_the_future(make_session):
    now = datetime(2026, 10, 10, 3, 0)  # Oct 9, 20:00 in Los Angeles
    _add_user(make_session, None, streak_count=5, streak_last_active=date(2026, 10, 10))
    db = make_session()
    user = db.query(User).first()
    rebase_for_timezone(user, None, ZoneInfo("America/Los_Angeles"), now=now)
    user.timezone = "America/Los_Angeles"
    assert user.streak_last_active == date(2026, 10, 9)
    record_activity(user, db, now=now)
    assert user.streak_count == 5  # already counted on this local day


def test_last_active_ahead_of_today_counts_as_today(make_session):
    """A date left in the local future by an older zone switch is not a gap."""
    _add_user(
        make_session,
        "America/Los_Angeles",
        streak_count=5,
        streak_last_active=date(2026, 10, 11),
    )
    db = make_session()
    user = db.query(User).first()
    now = at("America/Los_Angeles", date(2026, 10, 10), 20)
    assert current_streak(user, now=now) == 5
    record_activity(user, db, now=now)
    assert user.streak_count == 5


# ---- daily auto-enrol --------------------------------------------------------


@pytest.fixture
def hsk_fixture(swap_dictionaries):
    swap_dictionaries(
        hsk={
            w: {"level_new": "new-1", "pinyin": f"p{i}", "meaning": f"m{i}"}
            for i, w in enumerate("一二三四五六")
        }
    )


@pytest.mark.parametrize("tz", ZONES)
def test_auto_enrol_once_per_local_day(make_session, hsk_fixture, tz):
    _add_user(make_session, tz, daily_new_words=2)
    db = make_session()
    user = db.query(User).first()

    assert len(enrollment.enroll_daily_words(user, db, now=at(tz, DAY, 23, 30))) == 2
    db.commit()
    assert enrollment.enroll_daily_words(user, db, now=at(tz, DAY, 23, 50)) == []
    assert enrollment.enrolled_today(user, db, now=at(tz, DAY, 23, 50)) == 2

    next_day = at(tz, DAY + timedelta(1), 0, 10)
    assert enrollment.enrolled_today(user, db, now=next_day) == 0
    assert len(enrollment.enroll_daily_words(user, db, now=next_day)) == 2


# ---- weekly sparkline ------------------------------------------------------


@pytest.mark.parametrize("tz", ZONES)
def test_weekly_buckets_are_local_days(api, clock, tz):
    client, Session = api
    _add_user(Session, tz)
    _add(
        Session,
        UserWordEvent(
            user_id=1,
            word="a",
            event_type="review",
            grade=3,
            created_at=at(tz, DAY - timedelta(1), 23, 50),
        ),
        UserWordEvent(
            user_id=1, word="b", event_type="review", grade=3, created_at=at(tz, DAY, 0, 10)
        ),
        UserWordEvent(
            user_id=1,
            word="c",
            event_type="state_change",
            new_state="known",
            created_at=at(tz, DAY, 0, 20),
        ),
        # Before the window's first local day: left out.
        UserWordEvent(
            user_id=1,
            word="d",
            event_type="review",
            grade=3,
            created_at=at(tz, DAY - timedelta(6), 0, 0) - timedelta(minutes=1),
        ),
    )
    clock(at(tz, DAY, 1, 0))
    days = client.get("/api/stats/weekly").json()["days"]
    assert [d["date"] for d in days][-1] == DAY.isoformat()
    assert days[0]["date"] == (DAY - timedelta(6)).isoformat()
    assert (days[-1]["reviews"], days[-1]["marked_known"]) == (1, 1)
    assert (days[-2]["reviews"], days[-2]["marked_known"]) == (1, 0)
    assert sum(d["reviews"] for d in days) == 2


# ---- settings ----------------------------------------------------------------


def test_timezone_setting_round_trip_and_validation(api):
    client, Session = api
    _add_user(Session, None)
    assert client.get("/api/auth/me").json()["user"]["timezone"] is None

    r = client.patch("/api/auth/me/settings", json={"timezone": "Europe/Vienna"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["user"]["timezone"] == "Europe/Vienna"

    for bad in ["Mars/Olympus_Mons", "Europe/../etc/passwd", "x" * 100]:
        r = client.patch("/api/auth/me/settings", json={"timezone": bad})
        assert r.status_code == 400, bad
    assert _user(Session).timezone == "Europe/Vienna"

    # Other settings leave it alone.
    client.patch("/api/auth/me/settings", json={"review_window": "now"})
    assert _user(Session).timezone == "Europe/Vienna"
