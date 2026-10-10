"""
SRS review router — queue ordering, grade roundtrip, stats endpoint.

We don't try to verify FSRS's math here (that's the upstream library's
job); we just verify our wiring: a graded card's due_at moves forward,
the queue stops returning it, and stats reflect the action.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user, require_auth
from app.database import Base, User, UserWord, get_db


@pytest.fixture
def review_client(app_module):
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
    # Seed: two due cards (no due_at means brand-new in queue), one already
    # due in the past, one due far in the future (should NOT appear), one
    # ignored (should NOT appear). Known-with-due-in-the-past also appears
    # in the queue now that 'known' is just a high-stability SRS state.
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
            yield c, TestingSession
    finally:
        app_module.dependency_overrides.clear()


def test_queue_returns_only_due_active_cards(review_client):
    client, _ = review_client
    r = client.get("/api/review/queue")
    assert r.status_code == 200, r.text
    words = [c["word"] for c in r.json()["cards"]]
    assert "一" in words and "二" in words
    assert "三" not in words, "future-due card leaked into queue"
    assert "忽略" not in words, "ignored card leaked into queue"
    assert "远期" not in words, "future-due known card leaked into queue"


def test_queue_orders_nulls_first(review_client):
    client, _ = review_client
    r = client.get("/api/review/queue")
    words = [c["word"] for c in r.json()["cards"]]
    # 一 has due_at=NULL, 二 has due_at in the past — NULLs come first so
    # never-reviewed-but-learning words get attention before old laggards.
    assert words.index("一") < words.index("二")


def test_grade_updates_due_at_and_removes_from_queue(review_client):
    """Phase 1.3b — every grade advances FSRS immediately; the prompt
    stage on the queue side picks which modality to render, the grade
    endpoint stays simple."""
    client, Session = review_client
    r = client.post("/api/review/grade", json={"word": "一", "grade": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["word"] == "一"
    assert body["due_at"] is not None
    assert body["stability"] is not None and body["stability"] > 0
    # Stage progresses with stability — a fresh Good lands the card in
    # 'trace' (1d ≤ s < 10d) on typical FSRS-4.5 defaults.
    assert body["prompt_stage"] in ("intro", "trace", "produce")

    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "一").one()
        assert row.due_at is not None
        assert row.due_at > datetime.utcnow() - timedelta(seconds=1)
        assert row.fsrs_state is not None
    finally:
        db.close()


def test_grade_rejects_untracked_word(review_client):
    """Grading never invents rows: a word the user isn't tracking is a 404,
    an ignored one a 409, and neither touches FSRS or the streak."""
    client, Session = review_client
    r = client.post(
        "/api/review/grade",
        json={"word": "新词", "grade": 4, "mode": "recognition"},
    )
    assert r.status_code == 404
    r = client.post("/api/review/grade", json={"word": "忽略", "grade": 4})
    assert r.status_code == 409
    db = Session()
    try:
        assert db.query(UserWord).filter(UserWord.word == "新词").count() == 0
        ignored = db.query(UserWord).filter(UserWord.word == "忽略").one()
        assert ignored.state == "ignored"
        assert ignored.due_at is None
    finally:
        db.close()


def test_mixed_queue_does_not_scan_saved_texts(review_client, monkeypatch):
    """Mixed mode never shows a cloze step, so building its queue must not
    go looking for sample sentences."""
    from app.services import cloze

    def _fail(row, db):
        raise AssertionError("mixed queue scanned saved texts")

    monkeypatch.setattr(cloze, "populate_sample_sentence", _fail)
    client, _ = review_client
    r = client.get("/api/review/queue?mode=mixed")
    assert r.status_code == 200, r.text
    assert r.json()["cards"]


def test_mixed_queue_keeps_cached_sample_sentence(review_client):
    client, Session = review_client
    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "一").one()
        row.sample_sentence = "一个人。"
        db.commit()
    finally:
        db.close()
    cards = client.get("/api/review/queue?mode=mixed").json()["cards"]
    card = next(c for c in cards if c["word"] == "一")
    assert card["has_sample_sentence"] is True
    assert card["cloze_template"] == "___个人。"


def test_cloze_queue_populates_sentences(review_client):
    from app.database import SavedText

    client, Session = review_client
    db = Session()
    try:
        db.add(SavedText(user_id=1, title="t", content="二月很冷。", analysis_data="{}"))
        db.commit()
    finally:
        db.close()
    cards = client.get("/api/review/queue?mode=cloze").json()["cards"]
    assert [c["word"] for c in cards] == ["二"]
    assert cards[0]["cloze_sentence"] == "二月很冷。"


def test_queue_handler_runs_off_the_event_loop():
    """The queue does sync DB work (enrolment, backfill, sentence lookup);
    a plain `def` handler lets FastAPI run it in the threadpool."""
    import inspect

    from app.routers import review

    assert not inspect.iscoroutinefunction(review.review_queue)
    assert not inspect.iscoroutinefunction(review.practice_card)


def test_prompt_stage_progression(review_client):
    """A brand-new card lands in 'intro'; once FSRS pushes stability
    past one day, the card flips to 'trace'."""
    from app.services.srs import prompt_stage_for

    assert prompt_stage_for(None) == "intro"
    assert prompt_stage_for(0.5) == "intro"
    assert prompt_stage_for(1.0) == "trace"
    assert prompt_stage_for(5.0) == "trace"
    assert prompt_stage_for(9.99) == "trace"
    assert prompt_stage_for(10.0) == "produce"
    assert prompt_stage_for(180.0) == "produce"


def test_invalid_grade_rejected(review_client):
    client, _ = review_client
    r = client.post("/api/review/grade", json={"word": "一", "grade": 7})
    assert r.status_code == 400


def test_stats_endpoint(review_client):
    client, _ = review_client
    r = client.get("/api/review/stats")
    assert r.status_code == 200
    body = r.json()
    # learning counter is just state='learning' rows ('一', '二', '三').
    assert body["learning"] == 3
    # 2 are due now ('一' null + '二' past); '三' is future-due, the known
    # row is future-due, the ignored row never appears.
    assert body["due_now"] == 2
    # No reviews yet -> 0.
    assert body["reviewed_today"] == 0

    # Grade one (single-mode so FSRS advances and the card moves out of
    # 'due now' immediately — mixed-mode would need four grades).
    client.post(
        "/api/review/grade",
        json={"word": "一", "grade": 3, "cycle": False},
    )
    body2 = client.get("/api/review/stats").json()
    assert body2["reviewed_today"] == 1
    assert body2["due_now"] == 1  # '一' moved out of the due window


def test_queue_meanings_cap_skips_headline_not_index_zero(review_client, monkeypatch):
    """The headline is not always meanings[0] (here it is the sixth).
    The card keeps the headline's own sense plus up to four others, and
    register tags stripped off the headline ride along as meaning_tags."""
    from app import state

    client, session_factory = review_client
    db = session_factory()
    db.add(UserWord(user_id=1, word="号", state="learning"))
    db.commit()
    db.close()
    senses = [
        "(literary) to call out",
        "(bound form) bugle",
        "to mark; to label",
        "day of the month",
        "number in a series",
        "size",
        "mark; sign",
    ]
    monkeypatch.setitem(
        state.hsk_vocab,
        "号",
        {
            "pinyin": "hào",
            "meaning": "size",
            "meanings": senses,
            "meaning_tags": [],
            "level": "1",
        },
    )
    monkeypatch.setitem(
        state.hsk_vocab,
        "一",
        {
            "pinyin": "yī",
            "meaning": "one",
            "meanings": ["(bound form) one", "single"],
            "meaning_tags": ["bound form"],
            "level": "1",
        },
    )
    r = client.get("/api/review/queue")
    assert r.status_code == 200, r.text
    cards = {c["word"]: c for c in r.json()["cards"]}
    hao = cards["号"]
    assert hao["meaning"] == "size"
    # Headline sense + the first four others; the rest drop.
    assert hao["meanings"] == [*senses[:4], "size"]
    assert hao["meaning_tags"] == []
    yi = cards["一"]
    assert yi["meaning"] == "one"
    assert yi["meaning_tags"] == ["bound form"]
