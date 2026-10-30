"""
POST /api/words/import-hsk — bulk-mark HSK levels as known. We seed a
small in-memory HSK vocab so the test doesn't depend on the bundled
data or on real-world counts.
"""

import pytest

from app import state as _state
from app.database import User, UserWord

# A few canonical HSK entries spanning levels.
_SAMPLE_VOCAB = {
    "你": {"level_new": "new-1"},
    "好": {"level_new": "new-1"},
    "今天": {"level_new": "new-1"},
    "学习": {"level_new": "new-2"},
    "汉字": {"level_new": "new-3"},
    "复杂": {"level_new": "new-4"},
    "高级": {"level_new": "new-5"},
    "繁": {"level_old": "old-3"},
    "體": {"level_old": "old-4"},
}


@pytest.fixture
def import_client(memory_db, open_client):
    """Stand up an isolated DB + auth + seeded HSK vocab for these tests."""
    TestingSession = memory_db

    db = TestingSession()
    db.add(User(id=1, username="alice", password_hash="x", invite_quota=0))
    db.commit()
    db.close()

    # Opening the client runs startup, which refills hsk_vocab from the
    # loader, so the seeded vocab goes in afterwards.
    c = open_client(TestingSession)
    saved = dict(_state.hsk_vocab)
    _state.hsk_vocab.clear()
    _state.hsk_vocab.update(_SAMPLE_VOCAB)
    try:
        yield c, TestingSession
    finally:
        _state.hsk_vocab.clear()
        _state.hsk_vocab.update(saved)


def test_import_hsk_level_2_includes_levels_1_and_2(import_client):
    client, _ = import_client
    r = client.post("/api/words/import-hsk", json={"up_to_level": 2, "hsk_version": "new"})
    assert r.status_code == 200, r.text
    body = r.json()
    # 3 HSK 1 + 1 HSK 2 = 4 eligible from the seeded vocab.
    assert body["total_eligible"] == 4
    assert body["inserted"] == 4
    assert body["skipped"] == 0


def test_import_hsk_is_idempotent(import_client):
    client, _ = import_client
    client.post("/api/words/import-hsk", json={"up_to_level": 1, "hsk_version": "new"})
    r = client.post("/api/words/import-hsk", json={"up_to_level": 1, "hsk_version": "new"})
    body = r.json()
    assert body["inserted"] == 0
    assert body["skipped"] == 3  # already known


def test_import_old_hsk_uses_level_old_field(import_client):
    client, _ = import_client
    r = client.post("/api/words/import-hsk", json={"up_to_level": 3, "hsk_version": "old"})
    body = r.json()
    # 繁 is old-3 → in. 體 is old-4 → out.
    assert body["total_eligible"] == 1
    assert body["inserted"] == 1


def test_invalid_level_rejected(import_client):
    client, _ = import_client
    assert (
        client.post(
            "/api/words/import-hsk", json={"up_to_level": 99, "hsk_version": "new"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/words/import-hsk", json={"up_to_level": 1, "hsk_version": "??"}
        ).status_code
        == 400
    )


def test_words_land_as_known_state(import_client):
    client, Session = import_client
    client.post("/api/words/import-hsk", json={"up_to_level": 1, "hsk_version": "new"})
    db = Session()
    try:
        rows = db.query(UserWord).filter(UserWord.user_id == 1).all()
        assert {r.state for r in rows} == {"known"}
        assert {r.word for r in rows} == {"你", "好", "今天"}
    finally:
        db.close()


def test_import_hsk_counts_every_word_in_weekly_stats(import_client):
    """The import logs one event for many words; the weekly marked_known
    count adds up the words, not the events."""
    client, _ = import_client
    client.post("/api/words/import-hsk", json={"up_to_level": 2, "hsk_version": "new"})
    days = client.get("/api/stats/weekly").json()["days"]
    assert days[-1]["marked_known"] == 4
