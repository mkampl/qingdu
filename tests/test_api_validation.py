"""
Request validation for the write endpoints that take JSON bodies:
vocabulary lists, saved texts, snooze, review-now, review grading, and the input caps
on analyze / translate / TTS.
"""

import json
from datetime import datetime

import pytest

from app.database import SavedText, User, UserWord, VocabularyList


@pytest.fixture
def api(memory_db, open_client):
    TestingSession = memory_db

    db = TestingSession()
    db.add(User(id=1, username="alice", password_hash="x", invite_quota=0))
    db.add(
        VocabularyList(
            id=5,
            user_id=1,
            name="Lesson",
            list_type="custom",
            sections=json.dumps(
                [
                    {
                        "name": "Main",
                        "words": [
                            {"hanzi": "你好", "pinyin": "nǐ hǎo", "meaning": "hello"},
                            {"hanzi": "再见", "pinyin": "zài jiàn", "meaning": "bye"},
                        ],
                    },
                    {"name": "Extra", "words": []},
                ]
            ),
        )
    )
    db.add(UserWord(user_id=1, word="学习", state="learning"))
    db.add(UserWord(user_id=1, word="忽略", state="ignored"))
    db.commit()
    db.close()

    return open_client(TestingSession), TestingSession


def _sections(Session, list_id=5):
    s = Session()
    try:
        return json.loads(s.get(VocabularyList, list_id).sections)
    finally:
        s.close()


# ---- vocabulary lists ---------------------------------------------------


def test_create_list_requires_name(api):
    client, _ = api
    assert client.post("/api/vocabulary-lists", json={}).status_code == 422
    assert client.post("/api/vocabulary-lists", json={"name": "   "}).status_code == 422
    r = client.post("/api/vocabulary-lists", json={"name": "HSK 3"})
    assert r.status_code == 200, r.text


def test_create_list_rejects_malformed_sections(api):
    client, _ = api
    r = client.post("/api/vocabulary-lists", json={"name": "x", "sections": [{"words": []}]})
    assert r.status_code == 422


def test_update_list_rejects_section_without_name(api):
    client, Session = api
    r = client.put("/api/vocabulary-lists/5", json={"sections": [{"words": []}]})
    assert r.status_code == 422
    assert [s["name"] for s in _sections(Session)] == ["Main", "Extra"]


def test_update_list_keeps_patch_semantics(api):
    client, Session = api
    r = client.put("/api/vocabulary-lists/5", json={"apply_as_glossary": True})
    assert r.status_code == 200, r.text
    assert len(_sections(Session)) == 2


def test_add_word_missing_hanzi_is_422(api):
    client, _ = api
    r = client.post("/api/vocabulary-lists/5/words", json={"section_name": "Main"})
    assert r.status_code == 422


def test_add_word_missing_section_is_422(api):
    client, Session = api
    r = client.post("/api/vocabulary-lists/5/words", json={"hanzi": "谢谢"})
    assert r.status_code == 422
    assert all(s["name"] for s in _sections(Session))


def test_add_word_duplicate_in_section_is_409(api):
    client, Session = api
    r = client.post(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Main", "hanzi": "你好", "meaning": "hi"},
    )
    assert r.status_code == 409
    assert "Main" in r.json()["detail"]
    assert len(_sections(Session)[0]["words"]) == 2


def test_add_word_duplicate_in_other_section_is_409(api):
    client, Session = api
    r = client.post(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Extra", "hanzi": "你好", "meaning": ""},
    )
    assert r.status_code == 409
    assert "Main" in r.json()["detail"]
    assert _sections(Session)[1]["words"] == []


def test_add_word_success_reports_added(api):
    client, Session = api
    r = client.post(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Extra", "hanzi": "谢谢", "meaning": "thanks"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["added"] is True
    assert r.json()["pinyin"].startswith("xiè")
    assert _sections(Session)[1]["words"][0]["hanzi"] == "谢谢"


def test_add_section_duplicate_is_409(api):
    client, _ = api
    assert client.post("/api/vocabulary-lists/5/sections", json={}).status_code == 422
    r = client.post("/api/vocabulary-lists/5/sections", json={"name": "Main"})
    assert r.status_code == 409


def test_rename_section_collision_is_409(api):
    client, _ = api
    r = client.put(
        "/api/vocabulary-lists/5/sections",
        json={"old_name": "Extra", "new_name": "Main"},
    )
    assert r.status_code == 409
    r = client.put("/api/vocabulary-lists/5/sections", json={"old_name": "Extra"})
    assert r.status_code == 422


def test_update_word_hanzi_collision_is_409(api):
    client, Session = api
    r = client.put(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Main", "old_hanzi": "再见", "word": {"hanzi": "你好"}},
    )
    assert r.status_code == 409
    assert [w["hanzi"] for w in _sections(Session)[0]["words"]] == ["你好", "再见"]


def test_update_word_meaning_only_still_works(api):
    client, Session = api
    r = client.put(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Main", "old_hanzi": "再见", "word": {"meaning": "goodbye"}},
    )
    assert r.status_code == 200, r.text
    assert _sections(Session)[0]["words"][1]["meaning"] == "goodbye"


def test_update_word_requires_fields(api):
    client, _ = api
    r = client.put("/api/vocabulary-lists/5/words", json={"section_name": "Main"})
    assert r.status_code == 422


def test_delete_word_requires_fields(api):
    client, _ = api
    r = client.request("DELETE", "/api/vocabulary-lists/5/words", json={"hanzi": "你好"})
    assert r.status_code == 422


def test_list_mutation_survives_legacy_nameless_section(api):
    """A section stored without a name must not
    KeyError every later mutation."""
    client, Session = api
    s = Session()
    row = s.get(VocabularyList, 5)
    row.sections = json.dumps([{"words": []}, {"name": "Main", "words": []}])
    s.commit()
    s.close()
    r = client.post(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Main", "hanzi": "谢谢", "meaning": ""},
    )
    assert r.status_code == 200, r.text


# ---- saved texts --------------------------------------------------------


_ANALYSIS = {"words": [{"text": "学习", "is_hsk": True}, {"text": "。"}], "statistics": {}}


def test_save_text_requires_analysis_data(api):
    client, Session = api
    r = client.post("/api/texts/save", json={"title": "t", "content": "学习。"})
    assert r.status_code == 422
    r = client.post(
        "/api/texts/save",
        json={"title": "t", "content": "学习。", "analysis_data": None},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/texts/save",
        json={"title": "t", "content": "学习。", "analysis_data": {"statistics": {}}},
    )
    assert r.status_code == 422
    s = Session()
    try:
        assert s.query(SavedText).count() == 0
    finally:
        s.close()


def test_save_then_list_and_get(api):
    client, _ = api
    r = client.post(
        "/api/texts/save",
        json={"title": "t", "content": "学习。" * 200, "analysis_data": _ANALYSIS},
    )
    assert r.status_code == 200, r.text
    text_id = r.json()["id"]

    listing = client.get("/api/texts")
    assert listing.status_code == 200
    [summary] = listing.json()
    assert summary["id"] == text_id
    assert "analysisData" not in summary
    assert "content" not in summary
    assert summary["preview"].startswith("学习。")
    assert len(summary["preview"]) <= 200
    assert summary["total_unique"] == 1
    assert summary["known_unique"] == 0
    for key in ("title", "date", "tags", "reading_progress", "share_token", "glossary_list_ids"):
        assert key in summary

    full = client.get(f"/api/texts/{text_id}")
    assert full.status_code == 200
    body = full.json()
    assert body["content"] == "学习。" * 200
    assert body["analysisData"]["words"][0]["text"] == "学习"
    assert body["total_unique"] == 1


def test_get_text_404_for_missing(api):
    client, _ = api
    assert client.get("/api/texts/999").status_code == 404


def test_list_texts_skips_malformed_rows(api):
    client, Session = api
    s = Session()
    s.add(SavedText(id=1, user_id=1, title="bad", content="x", analysis_data="null"))
    s.add(SavedText(id=2, user_id=1, title="worse", content="x", analysis_data="{not json"))
    s.add(
        SavedText(
            id=3,
            user_id=1,
            title="good",
            content="学习。",
            analysis_data=json.dumps(_ANALYSIS),
        )
    )
    s.commit()
    s.close()
    r = client.get("/api/texts")
    assert r.status_code == 200, r.text
    assert [t["title"] for t in r.json()] == ["good"]


def test_delete_missing_text_is_404(api):
    client, _ = api
    assert client.delete("/api/texts/999").status_code == 404


def _saved_text(Session) -> int:
    s = Session()
    s.add(SavedText(id=9, user_id=1, title="t", content="学习。", analysis_data="{}"))
    s.commit()
    s.close()
    return 9


def test_update_text_changes_only_sent_fields(api):
    client, Session = api
    text_id = _saved_text(Session)
    r = client.patch(f"/api/texts/{text_id}", json={"title": "new", "tags": ["a"]})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": text_id, "title": "new", "message": "Text updated"}
    s = Session()
    text = s.get(SavedText, text_id)
    assert (text.title, text.tags, text.content) == ("new", '["a"]', "学习。")
    s.close()


@pytest.mark.parametrize(
    "body",
    [
        {"tags": "a"},
        {"reading_progress": "half"},
        {"folder_id": "x"},
        {"analysis_data": None},
        {"analysis_data": {"statistics": {}}},
    ],
)
def test_update_text_rejects_bad_fields(api, body):
    client, Session = api
    text_id = _saved_text(Session)
    assert client.patch(f"/api/texts/{text_id}", json=body).status_code == 422


# ---- snooze -------------------------------------------------------------


@pytest.mark.parametrize("days", ["abc", 0, -1, 366, 2.5])
def test_snooze_rejects_bad_days(api, days):
    client, _ = api
    r = client.post("/api/words/snooze", json={"word": "学习", "days": days})
    assert r.status_code == 422, r.text


def test_snooze_accepts_valid_days(api):
    client, _ = api
    r = client.post("/api/words/snooze", json={"word": "学习", "days": 120})
    assert r.status_code == 200, r.text
    assert r.json()["days"] == 120
    r = client.post("/api/words/snooze", json={"word": "学习"})
    assert r.json()["days"] == 3


def test_snooze_requires_word(api):
    client, _ = api
    assert client.post("/api/words/snooze", json={"days": 3}).status_code == 422


def test_review_now_sets_word_due(api):
    client, _ = api
    r = client.post("/api/words/review-now", json={"word": "学习"})
    assert r.status_code == 200, r.text
    assert r.json()["word"] == "学习"
    assert r.json()["due_at"]


@pytest.mark.parametrize("body", [{}, {"word": 3}])
def test_review_now_rejects_bad_body(api, body):
    client, _ = api
    assert client.post("/api/words/review-now", json=body).status_code == 422


# ---- review grading -----------------------------------------------------


def test_grade_unknown_word_is_404_and_creates_nothing(api):
    client, Session = api
    r = client.post("/api/review/grade", json={"word": "随便", "grade": 3})
    assert r.status_code == 404
    s = Session()
    try:
        assert s.query(UserWord).filter(UserWord.word == "随便").count() == 0
    finally:
        s.close()


def test_grade_ignored_word_is_409(api):
    client, Session = api
    r = client.post("/api/review/grade", json={"word": "忽略", "grade": 3})
    assert r.status_code == 409
    s = Session()
    try:
        row = s.query(UserWord).filter(UserWord.word == "忽略").one()
        assert row.state == "ignored"
        assert row.fsrs_state is None
        assert s.get(User, 1).streak_last_active is None
    finally:
        s.close()


def test_grade_learning_word_still_works(api):
    client, _ = api
    r = client.post("/api/review/grade", json={"word": "学习", "grade": 3})
    assert r.status_code == 200, r.text
    assert r.json()["due_at"] is not None
    assert datetime.fromisoformat(r.json()["due_at"][:19]) > datetime(2020, 1, 1)


# ---- input caps ---------------------------------------------------------


def test_analyze_rejects_oversized_text(api):
    from app.core.constants import MAX_ANALYZE_CHARS

    client, _ = api
    r = client.post("/api/analyze", json={"text": "中" * (MAX_ANALYZE_CHARS + 1)})
    assert r.status_code == 413
    assert str(MAX_ANALYZE_CHARS) in r.json()["detail"].replace(",", "")


def test_translate_rejects_oversized_text(api):
    from app.core.constants import MAX_TRANSLATE_CHARS

    client, _ = api
    r = client.post("/api/translate", json={"text": "中" * (MAX_TRANSLATE_CHARS + 1)})
    assert r.status_code == 413


def test_sentence_tts_rejects_oversized_text(api):
    from app.core.constants import MAX_TTS_CHARS

    client, _ = api
    r = client.post("/api/tts/sentence", json={"text": "中" * (MAX_TTS_CHARS + 1)})
    assert r.status_code == 413


def test_tts_error_does_not_leak_details(api, monkeypatch):
    from app.routers import tts as tts_router

    async def _boom(text):
        raise RuntimeError("upstream said: secret-internal-host:8443 refused")

    monkeypatch.setattr(tts_router, "fetch_chinese_tts", _boom)
    client, _ = api
    for r in (
        client.get("/api/tts/你好"),
        client.post("/api/tts/sentence", json={"text": "你好。"}),
    ):
        assert r.status_code == 502
        assert "secret" not in r.text
        assert r.json()["detail"] == "Text-to-speech is unavailable right now."
