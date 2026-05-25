"""
Phase #96 — daily HSK auto-enrollment.

We don't want to depend on the real HSK vocab being loaded in tests, so
each test patches `app.state.hsk_vocab` with a small fixture covering
two levels. The service walks low -> high and picks random within a
level; we verify counts + level progression + idempotency without
asserting which specific (random) word came out.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, User, UserWord, UserWordEvent
from app.services import enrollment
from app.state import hsk_vocab


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def hsk_fixture():
    """Stub two HSK-1 words and two HSK-2 words, then restore."""
    original = dict(hsk_vocab)
    hsk_vocab.clear()
    hsk_vocab.update(
        {
            "我": {"level_new": "new-1", "pinyin": "wǒ", "meaning": "I"},
            "你": {"level_new": "new-1", "pinyin": "nǐ", "meaning": "you"},
            "他": {"level_new": "new-2", "pinyin": "tā", "meaning": "he"},
            "她": {"level_new": "new-2", "pinyin": "tā", "meaning": "she"},
        }
    )
    yield
    hsk_vocab.clear()
    hsk_vocab.update(original)


def _make_user(db, daily_new_words=5, hsk_focus_version="new"):
    u = User(
        id=1,
        username="alice",
        password_hash="x",
        is_admin=False,
        must_change_password=False,
        invite_quota=0,
        daily_new_words=daily_new_words,
        hsk_focus_version=hsk_focus_version,
    )
    db.add(u)
    db.commit()
    return u


def test_enrolls_up_to_target_from_lowest_level(db_session, hsk_fixture):
    u = _make_user(db_session, daily_new_words=3)
    enrolled = enrollment.enroll_daily_words(u, db_session)
    db_session.commit()
    # Only 2 HSK-1 words in fixture; the 3rd should spill into HSK-2.
    assert len(enrolled) == 3
    rows = db_session.query(UserWord).filter(UserWord.user_id == 1).all()
    assert {r.word for r in rows} == set(enrolled)
    # All inserted as 'learning' with no due_at (front of queue).
    assert all(r.state == "learning" and r.due_at is None for r in rows)


def test_target_zero_is_noop(db_session, hsk_fixture):
    u = _make_user(db_session, daily_new_words=0)
    enrolled = enrollment.enroll_daily_words(u, db_session)
    assert enrolled == []
    assert db_session.query(UserWord).count() == 0


def test_idempotent_within_same_day(db_session, hsk_fixture):
    u = _make_user(db_session, daily_new_words=2)
    enrolled_first = enrollment.enroll_daily_words(u, db_session)
    db_session.commit()
    enrolled_second = enrollment.enroll_daily_words(u, db_session)
    db_session.commit()
    # Already at target; second call adds nothing.
    assert len(enrolled_first) == 2
    assert enrolled_second == []
    assert db_session.query(UserWord).count() == 2


def test_skips_words_user_has_already_touched(db_session, hsk_fixture):
    u = _make_user(db_session, daily_new_words=4)
    # Pre-touch one HSK-1 and one HSK-2 word.
    db_session.add(UserWord(user_id=1, word="我", state="known"))
    db_session.add(UserWord(user_id=1, word="他", state="learning"))
    db_session.commit()

    enrolled = enrollment.enroll_daily_words(u, db_session)
    db_session.commit()
    # 4 total in fixture, 2 already touched -> only 2 left to enrol.
    assert set(enrolled) == {"你", "她"}


def test_enrolled_today_reflects_event_log(db_session, hsk_fixture):
    u = _make_user(db_session, daily_new_words=2)
    enrollment.enroll_daily_words(u, db_session)
    db_session.commit()
    assert enrollment.enrolled_today(u, db_session) == 2

    # An auto_enroll event from yesterday shouldn't count toward today.
    yesterday = datetime.utcnow() - timedelta(days=1, hours=2)
    stale = UserWordEvent(
        user_id=1, word="老", event_type="auto_enroll", new_state="learning", created_at=yesterday
    )
    db_session.add(stale)
    db_session.commit()
    assert enrollment.enrolled_today(u, db_session) == 2
