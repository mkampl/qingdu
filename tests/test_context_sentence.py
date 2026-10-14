"""The sentence a word was marked in travels with it into review."""

from app.database import SavedText, UserWord
from tests.test_user_words import words_client as _words_client

words_client = _words_client  # the fixture, under the name the tests ask for


def _row(client, word):
    s = client.session_factory()
    try:
        return s.query(UserWord).filter(UserWord.word == word).one()
    finally:
        s.close()


def _card(client, word, mode="mixed"):
    cards = client.get("/api/review/queue", params={"mode": mode}).json()["cards"]
    return next(c for c in cards if c["word"] == word)


def test_marked_sentence_and_saved_text_title_reach_the_card(words_client):
    s = words_client.session_factory()
    s.add(SavedText(id=7, user_id=1, title="My diary", content="x", analysis_data="{}"))
    s.commit()
    s.close()

    r = words_client.post(
        "/api/words/state",
        json={"word": "中文", "state": "learning", "source_text_id": 7, "sentence": "我在学中文。"},
    )
    assert r.status_code == 200, r.text
    row = _row(words_client, "中文")
    assert (row.sample_sentence, row.sample_source) == ("我在学中文。", "My diary")

    card = _card(words_client, "中文")
    assert card["cloze_sentence"] == "我在学中文。"
    assert card["sentence_source"] == "My diary"


def test_library_slug_names_the_library_text(words_client):
    words_client.post(
        "/api/words/state",
        json={
            "word": "周末",
            "state": "learning",
            "sentence": "在现在，我喜欢周末。",
            "library_slug": "hsk1_01_school",
        },
    )
    from app.services import library

    title = library.get("hsk1_01_school")["title"]
    assert title
    assert _row(words_client, "周末").sample_source == title


def test_another_users_text_is_not_named(words_client):
    s = words_client.session_factory()
    s.add(SavedText(id=8, user_id=2, title="Bob's secret", content="x", analysis_data="{}"))
    s.commit()
    s.close()
    words_client.post(
        "/api/words/state",
        json={"word": "中文", "state": "learning", "source_text_id": 8, "sentence": "我在学中文。"},
    )
    assert _row(words_client, "中文").sample_source is None


def test_a_later_click_keeps_the_first_sentence(words_client):
    for sentence in ("我在学中文。", "她也学中文。"):
        words_client.post(
            "/api/words/state",
            json={"word": "中文", "state": "learning", "sentence": sentence},
        )
    assert _row(words_client, "中文").sample_sentence == "我在学中文。"


def test_mixed_cards_get_a_library_sentence_when_none_was_marked(words_client):
    words_client.post("/api/words/state", json={"word": "感冒", "state": "learning"})
    card = _card(words_client, "感冒")
    assert "感冒" in card["cloze_sentence"]
    assert card["sentence_source"]
