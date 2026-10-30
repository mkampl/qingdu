"""
SRS review router — queue ordering, grade roundtrip, stats endpoint.

We don't try to verify FSRS's math here (that's the upstream library's
job); we just verify our wiring: a graded card's due_at moves forward,
the queue stops returning it, and stats reflect the action.
"""

from datetime import UTC, datetime, timedelta

from app.database import User, UserWord, UserWordEvent
from app.routers.review import KNOWN_STABILITY_THRESHOLD_DAYS, next_state_after_grade
from app.services import srs
from app.services.timestamps import iso_utc


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
    """Every grade advances FSRS immediately; the prompt
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


def test_mixed_queue_finds_and_stores_sample_sentences(review_client):
    """Mixed cards show the word's sentence once the answer is out, so the
    queue looks one up for rows without one and keeps it on the row."""
    from app.database import SavedText

    client, Session = review_client
    _add(Session, SavedText(user_id=1, title="Winter", content="二月很冷。", analysis_data="{}"))
    cards = client.get("/api/review/queue?mode=mixed").json()["cards"]
    card = next(c for c in cards if c["word"] == "二")
    assert card["cloze_sentence"] == "二月很冷。"
    assert card["sentence_source"] == "Winter"
    db = Session()
    try:
        assert db.query(UserWord).filter(UserWord.word == "二").one().sample_sentence
    finally:
        db.close()


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


def test_cloze_queue_populates_sentences(review_client, monkeypatch):
    from app.database import SavedText
    from app.services import library

    # Saved texts only: the library fallback would give 一 a sentence too.
    monkeypatch.setattr(library, "example_sentence", lambda word, max_level=None: None)

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


def test_queue_card_carries_readings_with_card_reading_on_top(review_client, monkeypatch):
    """A polyphone card lists every reading for the card back; the one
    the card is graded on (its stored pinyin) comes first as main."""
    from app import state

    client, session_factory = review_client
    db = session_factory()
    db.add(UserWord(user_id=1, word="长", state="learning", pinyin="cháng", meaning="long"))
    db.commit()
    db.close()
    readings = [
        {
            "pinyin": "cháng",
            "primary": "long",
            "meanings": ["long"],
            "meaning_tags": [],
            "is_main": True,
        },
        {
            "pinyin": "zhǎng",
            "primary": "chief",
            "meanings": ["chief", "to grow"],
            "meaning_tags": [],
            "is_main": False,
            "example": {"word": "校长", "pinyin": "xiào zhǎng", "meaning": "principal"},
        },
    ]
    monkeypatch.setitem(
        state.hsk_vocab,
        "长",
        {"pinyin": "cháng", "meaning": "long", "meanings": ["long"], "readings": readings},
    )
    r = client.get("/api/review/queue")
    assert r.status_code == 200, r.text
    card = next(c for c in r.json()["cards"] if c["word"] == "长")
    assert [(x["pinyin"], x["is_main"]) for x in card["readings"]] == [
        ("cháng", True),
        ("zhǎng", False),
    ]
    assert card["readings"][1]["example"]["word"] == "校长"
    # Cards for single-reading words carry no readings list.
    one = next(c for c in r.json()["cards"] if c["word"] == "一")
    assert one["readings"] is None


# --- Review correctness: timestamps, hysteresis, cloze fill, windows, weekly stats


def _set_user(Session, **fields):
    db = Session()
    try:
        user = db.query(User).filter(User.id == 1).one()
        for k, v in fields.items():
            setattr(user, k, v)
        db.commit()
    finally:
        db.close()


def _add(Session, *rows):
    db = Session()
    try:
        for r in rows:
            db.add(r)
        db.commit()
    finally:
        db.close()


# --- timestamps -------------------------------------------------------------


def test_iso_utc_marks_naive_datetimes_as_utc():
    assert iso_utc(None) is None
    assert iso_utc(datetime(2026, 3, 1, 23, 30)) == "2026-03-01T23:30:00Z"
    aware = datetime(2026, 3, 1, 18, 30, tzinfo=UTC).astimezone()
    assert iso_utc(aware) == "2026-03-01T18:30:00Z"


def test_review_and_words_timestamps_carry_utc_offset(review_client):
    client, _ = review_client
    cards = client.get("/api/review/queue").json()["cards"]
    dated = [c for c in cards if c["due_at"]]
    assert dated and all(c["due_at"].endswith("Z") for c in dated)

    graded = client.post("/api/review/grade", json={"word": "一", "grade": 1}).json()
    assert graded["due_at"].endswith("Z")
    # Again schedules within minutes; read as UTC that is close to now.
    due = datetime.fromisoformat(graded["due_at"].replace("Z", "+00:00"))
    assert abs((due - datetime.now(UTC)).total_seconds()) < 30 * 60

    items = client.get("/api/words/queue").json()["items"]
    assert items
    for item in items:
        for key in ("due_at", "last_reviewed_at", "created_at"):
            if item[key]:
                assert item[key].endswith("Z"), (key, item[key])


# --- hysteresis -------------------------------------------------------------


def test_next_state_after_grade_only_again_demotes_known():
    low = KNOWN_STABILITY_THRESHOLD_DAYS / 2
    assert next_state_after_grade("known", low, 2) == "known"
    assert next_state_after_grade("known", low, 3) == "known"
    assert next_state_after_grade("known", low, 1) == "learning"
    assert next_state_after_grade("learning", low, 4) == "learning"
    assert next_state_after_grade("learning", KNOWN_STABILITY_THRESHOLD_DAYS, 3) == "known"


def test_hard_on_known_card_keeps_it_known(review_client):
    client, Session = review_client
    seeded = srs.already_known_state(jitter_seed=1)
    _add(
        Session,
        UserWord(
            user_id=1,
            word="熟",
            state="known",
            fsrs_state=seeded["fsrs_state"],
            stability=seeded["stability"],
            difficulty=seeded["difficulty"],
            due_at=datetime.utcnow() - timedelta(minutes=1),
            last_reviewed_at=seeded["last_reviewed_at"],
        ),
    )
    r = client.post("/api/review/grade", json={"word": "熟", "grade": 2})
    assert r.status_code == 200, r.text
    # A same-day Hard really does drop stability under the threshold ...
    assert r.json()["stability"] < KNOWN_STABILITY_THRESHOLD_DAYS
    db = Session()
    try:
        row = db.query(UserWord).filter(UserWord.word == "熟").one()
        # ... but the card stays known.
        assert row.state == "known"
        assert (
            db.query(UserWordEvent)
            .filter(UserWordEvent.word == "熟", UserWordEvent.event_type == "state_change")
            .count()
            == 0
        )
    finally:
        db.close()

    # Again is a lapse: that one demotes.
    client.post("/api/review/grade", json={"word": "熟", "grade": 1})
    db = Session()
    try:
        assert db.query(UserWord).filter(UserWord.word == "熟").one().state == "learning"
    finally:
        db.close()


# --- cloze fills up to the limit --------------------------------------------


def test_cloze_queue_skips_sentence_less_rows_before_limit(review_client, monkeypatch):
    from app.database import SavedText
    from app.services import library

    monkeypatch.setattr(library, "example_sentence", lambda word, max_level=None: None)

    client, Session = review_client
    old = datetime.utcnow() - timedelta(days=10)
    # Five earlier-due cards that no saved text contains, then two that do.
    rows = [
        UserWord(user_id=1, word=f"无{i}", state="learning", due_at=old + timedelta(minutes=i))
        for i in range(5)
    ]
    rows += [
        UserWord(user_id=1, word="春", state="learning", due_at=old + timedelta(hours=1)),
        UserWord(user_id=1, word="秋", state="learning", due_at=old + timedelta(hours=2)),
    ]
    _add(Session, *rows, SavedText(user_id=1, title="t", content="春天来了。秋天走了。"))
    # 一 / 二 from the base fixture have no sentence either.
    cards = client.get("/api/review/queue?mode=cloze&limit=2").json()["cards"]
    assert [c["word"] for c in cards] == ["春", "秋"]
    assert all(c["cloze_sentence"] for c in cards)
    # The sentences found on the way are stored on the rows.
    db = Session()
    try:
        assert db.query(UserWord).filter(UserWord.word == "春").one().sample_sentence
    finally:
        db.close()


# --- one window definition -------------------------------------------------


def test_window_counts_match_queue(review_client):
    client, Session = review_client
    now = datetime.utcnow()
    end_of_today = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    _add(
        Session,
        # Due tomorrow (mid-day): only the 'tomorrow' window covers it.
        UserWord(user_id=1, word="明", state="learning", due_at=end_of_today + timedelta(hours=12)),
        # Due the day after tomorrow: outside every window.
        UserWord(
            user_id=1,
            word="后",
            state="learning",
            due_at=end_of_today + timedelta(days=1, hours=1),
        ),
    )
    for window in ("now", "today", "tomorrow"):
        _set_user(Session, review_window=window)
        stats = client.get("/api/review/stats").json()
        cards = client.get("/api/review/queue?limit=100").json()["cards"]
        assert stats["due_in_window"] == len(cards), window
        words = {c["word"] for c in cards}
        assert ("明" in words) is (window == "tomorrow")
        assert "后" not in words
    # due_today alone would undercount the 'tomorrow' window.
    assert stats["due_in_window"] > stats["due_today"]


def test_stats_in_rotation_counts_learning_and_known(review_client):
    client, _ = review_client
    body = client.get("/api/review/stats").json()
    # 一 二 三 learning + 远期 known; the ignored row is out.
    assert body["in_rotation"] == 4
    assert body["learning"] == 3


# --- weekly marked_known ---------------------------------------------------


def test_weekly_marked_known_counts_words_not_reviews(review_client):
    client, Session = review_client
    _add(
        Session,
        UserWordEvent(user_id=1, word="a", event_type="state_change", new_state="known"),
        UserWordEvent(user_id=1, word="b", event_type="bulk_mark_known", new_state="known"),
        UserWordEvent(
            user_id=1,
            word="hsk-new-<=L1",
            event_type="bulk_mark_known",
            new_state="known",
            word_count=300,
        ),
        # Reviewing a known card is not "marking it known".
        UserWordEvent(user_id=1, word="c", event_type="review", new_state="known", grade=3),
    )
    today = client.get("/api/stats/weekly").json()["days"][-1]
    assert today["marked_known"] == 302


def test_next_intervals_grow_with_the_grade():
    now = datetime.now(UTC)
    fresh = srs.next_intervals(None, now=now)
    assert fresh[1] <= fresh[2] <= fresh[3] < fresh[4]
    assert fresh[1] < 3600  # a new card comes back within the session
    reviewed = srs.apply_grade(None, 3)["fsrs_state"]
    again = srs.next_intervals(reviewed, now=now + timedelta(days=3))
    assert again[1] < again[3] < again[4]


def test_queue_cards_carry_the_intervals(review_client):
    client, _ = review_client
    cards = client.get("/api/review/queue").json()["cards"]
    assert cards and all(set(c["intervals"]) == {"1", "2", "3", "4"} for c in cards)
