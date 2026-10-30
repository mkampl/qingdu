"""Only words become user words.

Phrases such as 很多 or 洗衣服 are not in HSK or CC-CEDICT; creating a
UserWord for them is refused (422 for a single word, skipped in bulk and in
the external API). Dictionary words, single characters, the user's own
list words and words clicked in a package text are still accepted, and an
existing row can always be updated.
"""

import json

import pytest

from app.database import UserWord, VocabularyList
from app.services import lexicon
from tests.test_external_api import _mint_token


@pytest.fixture
def small_cedict(swap_dictionaries):
    """A few CC-CEDICT entries; the full dictionary is not loaded in tests,
    and without any CC-CEDICT the gate stays open."""
    swap_dictionaries(
        cedict={
            "大卫": {"pinyin": "dà wèi", "meaning": "David", "meanings": ["David"]},
            "一个": {"pinyin": "yī ge", "meaning": "a; an; one", "meanings": ["a; an; one"]},
        }
    )


def _row(client, word):
    db = client.session_factory()
    try:
        return db.query(UserWord).filter(UserWord.user_id == 1, UserWord.word == word).first()
    finally:
        db.close()


def test_phrase_is_rejected(words_client, small_cedict):
    r = words_client.post("/api/words/state", json={"word": "很多", "state": "learning"})
    assert r.status_code == 422
    assert "很多" in r.json()["detail"]
    assert _row(words_client, "很多") is None


@pytest.mark.parametrize("word", ["衣服", "大卫", "一个", "龘"])
def test_dictionary_words_and_single_chars_are_accepted(
    words_client,
    small_cedict,
    word,
):
    r = words_client.post("/api/words/state", json={"word": word, "state": "learning"})
    assert r.status_code == 200, r.text
    assert _row(words_client, word) is not None


def test_own_list_word_is_accepted(words_client, small_cedict):
    db = words_client.session_factory()
    db.add(
        VocabularyList(
            user_id=1,
            name="Chores",
            list_type="custom",
            sections=json.dumps([{"name": "a", "words": [{"hanzi": "洗衣服"}]}]),
        )
    )
    db.commit()
    db.close()
    r = words_client.post("/api/words/state", json={"word": "洗衣服", "state": "learning"})
    assert r.status_code == 200, r.text


def test_package_click_is_accepted(words_client, small_cedict):
    r = words_client.post(
        "/api/words/state",
        json={
            "word": "道可道",
            "state": "learning",
            "meaning": "the way that can be told",
            "translation_source": "package",
            "package_source": "ddj",
        },
    )
    assert r.status_code == 200, r.text


def test_existing_phrase_row_can_still_change_state(words_client, small_cedict):
    db = words_client.session_factory()
    db.add(UserWord(user_id=1, word="很多", state="learning"))
    db.commit()
    db.close()
    r = words_client.post("/api/words/state", json={"word": "很多", "state": "ignored"})
    assert r.status_code == 200, r.text
    assert _row(words_client, "很多").state == "ignored"


def test_gate_open_without_cedict(words_client, swap_dictionaries):
    swap_dictionaries(cedict={})
    r = words_client.post("/api/words/state", json={"word": "很多", "state": "learning"})
    assert r.status_code == 200


def test_bulk_mark_known_skips_phrases(words_client, small_cedict):
    r = words_client.post("/api/words/bulk-mark-known", json={"words": ["很多", "衣服", "大卫"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped"] == ["很多"]
    assert body["updated"] == 2
    assert _row(words_client, "很多") is None
    assert _row(words_client, "衣服").state == "known"


def test_external_encountered_rejects_phrases(ext_client, small_cedict):
    token = _mint_token(ext_client, scopes="write:words")
    r = ext_client.post(
        "/api/external/words/encountered",
        json={"words": [{"word": "很多"}, {"word": "衣服"}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"accepted": ["衣服"], "rejected": ["很多"]}


def test_is_lexical_word_rules(words_client, small_cedict):
    assert lexicon.is_lexical_word("大卫")
    assert lexicon.is_lexical_word("我")
    assert not lexicon.is_lexical_word("很多")
    assert not lexicon.is_lexical_word("")
    assert lexicon.is_lexical_word("很多", extra={"很多"})
