"""Placement test: questions per level and marking the passed levels."""

import random

import pytest

from app.database import UserWord
from app.services import placement

VOCAB = {
    w: {"level_new": f"new-{lvl}", "level": f"new-{lvl}", "pinyin": p, "meaning": m}
    for w, lvl, p, m in [
        ("你好", 1, "nǐ hǎo", "hello"),
        ("谢谢", 1, "xiè xie", "to thank; thanks"),
        ("学生", 1, "xué sheng", "student"),
        ("老师", 1, "lǎo shī", "teacher"),
        ("朋友", 1, "péng you", "friend"),
        ("机场", 2, "jī chǎng", "airport"),
        ("比赛", 2, "bǐ sài", "competition (sports etc)"),
        ("帮助", 2, "bāng zhù", "to help"),
        ("告诉", 2, "gào su", "to tell"),
        ("宇宙", 7, "yǔ zhòu", "universe"),
    ]
}


@pytest.fixture
def vocab(words_client, swap_dictionaries):
    swap_dictionaries(hsk=VOCAB)
    return words_client


def test_items_ask_one_level_with_four_meanings(vocab):
    items = placement.items(1, 3, {"你好"}, random.Random(1))
    assert len(items) == 3
    for it in items:
        assert it["level"] == 1 and it["word"] != "你好"
        assert len(it["choices"]) == 4 and len(set(it["choices"])) == 4
        assert it["choices"][it["answer"]] == placement.short_meaning(VOCAB[it["word"]]["meaning"])


def test_short_meaning():
    assert placement.short_meaning("to rest; to stop") == "to rest"
    assert placement.short_meaning("competition (sports etc)") == "competition"


def test_finish_marks_the_passed_levels_known(vocab):
    r = vocab.post("/api/placement/finish", json={"level": 1})
    assert r.status_code == 200 and r.json()["inserted"] == 5
    s = vocab.session_factory()
    words = {w for (w,) in s.query(UserWord.word)}
    s.close()
    assert "你好" in words and "机场" not in words
    assert vocab.post("/api/placement/finish", json={"level": 0}).json()["inserted"] == 0


def test_items_endpoint(vocab):
    body = vocab.get("/api/placement/items", params={"level": 2, "n": 4}).json()
    assert len(body["items"]) == 4
