"""
record_activity drives the daily-streak counters. We use a tiny in-memory
DB so the SQL operations are real but the test stays hermetic.
"""

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, User
from app.services.streak import current_streak, record_activity


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def _user(db) -> User:
    user = User(username="alice", password_hash="x", invite_quota=0)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_first_activity_starts_streak_at_one():
    db = _session()
    user = _user(db)
    assert user.streak_count in (None, 0)
    record_activity(user, db)
    db.commit()
    db.refresh(user)
    assert user.streak_count == 1
    assert user.streak_last_active == datetime.utcnow().date()


def test_same_day_activity_is_idempotent():
    db = _session()
    user = _user(db)
    record_activity(user, db)
    record_activity(user, db)
    record_activity(user, db)
    db.commit()
    db.refresh(user)
    assert user.streak_count == 1


def test_consecutive_day_bumps_streak():
    db = _session()
    user = _user(db)
    yesterday = datetime.utcnow().date() - timedelta(days=1)
    user.streak_count = 5
    user.streak_last_active = yesterday
    db.commit()
    record_activity(user, db)
    db.commit()
    db.refresh(user)
    assert user.streak_count == 6


def test_lapsed_streak_resets_to_one():
    db = _session()
    user = _user(db)
    three_days_ago = datetime.utcnow().date() - timedelta(days=3)
    user.streak_count = 12
    user.streak_last_active = three_days_ago
    db.commit()
    record_activity(user, db)
    db.commit()
    db.refresh(user)
    assert user.streak_count == 1


def test_current_streak_returns_zero_if_stale():
    """The stored count is meaningless if the user hasn't acted in 2+ days."""
    db = _session()
    user = _user(db)
    user.streak_count = 9
    user.streak_last_active = datetime.utcnow().date() - timedelta(days=4)
    db.commit()
    assert current_streak(user) == 0


def test_current_streak_returns_value_when_active_today_or_yesterday():
    db = _session()
    user = _user(db)
    user.streak_count = 9
    user.streak_last_active = datetime.utcnow().date()
    db.commit()
    assert current_streak(user) == 9
    user.streak_last_active = datetime.utcnow().date() - timedelta(days=1)
    db.commit()
    assert current_streak(user) == 9
