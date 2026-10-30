"""Tone practice: items, choices and what is left out."""

import random

import pytest

from app import state
from app.services import tone_drill

VOCAB = {
    "买": {"pinyin": "mǎi", "meaning": "to buy", "level_new": "new-1"},
    "卖": {"pinyin": "mài", "meaning": "to sell", "level_new": "new-2"},
    "老师": {"pinyin": "lǎo shī", "meaning": "teacher", "level_new": "new-1"},
    "你好": {"pinyin": "nǐ hǎo", "meaning": "hello", "level_new": "new-1"},
    "一个": {"pinyin": "yī gè", "meaning": "one", "level_new": "new-1"},
    "朋友": {"pinyin": "péng you", "meaning": "friend", "level_new": "new-1"},
    "一会儿": {"pinyin": "yī huìr", "meaning": "a moment", "level_new": "new-1"},
}


@pytest.fixture
def vocab(words_client):
    saved = dict(state.hsk_vocab)
    state.hsk_vocab.clear()
    state.hsk_vocab.update(VOCAB)
    try:
        yield words_client
    finally:
        state.hsk_vocab.clear()
        state.hsk_vocab.update(saved)


def test_words_whose_tones_the_audio_would_not_match_are_left_out(vocab):
    # Two third tones (你好), 一, a neutral tone (朋友) and erhua.
    assert set(tone_drill.candidates()) == {"买", "卖", "老师"}


def test_choices_differ_only_in_tone_and_lead_with_real_words(vocab):
    pool = tone_drill.candidates()
    by_base = {}
    for c in pool.values():
        by_base.setdefault(tuple(s[:-1] for s in c.tones), []).append(c)
    opts, answer = tone_drill.choices(pool["买"], by_base, random.Random(3))
    assert len(opts) == 4
    assert opts[answer]["pinyin"] == "mǎi" and opts[answer]["word"] is None
    assert {"pinyin": "mài", "word": "卖"} in opts
    assert len({o["pinyin"] for o in opts}) == 4
    assert all(
        o["pinyin"].replace("ǎ", "a").replace("à", "a").replace("á", "a").replace("ā", "a") == "mai"
        for o in opts
    )


def test_the_endpoint_serves_the_users_words_first(vocab):
    vocab.post("/api/words/state", json={"word": "老师", "state": "learning"})
    items = vocab.get("/api/review/tones", params={"n": 1}).json()["items"]
    assert [i["word"] for i in items] == ["老师"]
    item = items[0]
    assert item["choices"][item["answer"]]["pinyin"] == "lǎo shī"
    # Topped up with everyday words that have a minimal pair.
    words = {i["word"] for i in vocab.get("/api/review/tones", params={"n": 5}).json()["items"]}
    assert words == {"老师", "买", "卖"}
