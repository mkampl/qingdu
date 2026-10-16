"""How much of a text a user can read, counted over running words."""

from app.database import UserWord
from app.services import readability
from tests.test_user_words import words_client as _words_client

words_client = _words_client


def _seed(client, **rows):
    s = client.session_factory()
    for word, (state, stability) in rows.items():
        s.add(UserWord(user_id=1, word=word, state=state, stability=stability))
    s.commit()
    s.close()


def _post(client, tokens, **extra):
    r = client.post("/api/readability", json={"tokens": tokens, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_counts_running_words_and_skips_punctuation(words_client):
    _seed(words_client, 我=("known", 90.0), 学习=("learning", 3.0))
    body = _post(words_client, ["我", "学习", "中文", "。", "我", "喜欢", "中文", "！", "abc", "3"])
    # 我 ×2 and 学习 known; 中文 ×2 and 喜欢 missing. Punctuation, Latin, digits ignored.
    assert body["total"] == 6
    assert body["known"] == 3
    assert body["in_progress"] == 0
    assert body["known_pct"] == 0.5
    assert [m["word"] for m in body["missing"]] == ["中文", "喜欢"]
    assert body["missing"][0]["count"] == 2
    assert body["unlocked"] is False


def test_fresh_learning_words_are_in_progress_not_known(words_client):
    _seed(words_client, 中文=("learning", None), 喜欢=("learning", 0.4), 我=("ignored", None))
    body = _post(words_client, ["我", "喜欢", "中文"])
    assert body["known"] == 1  # ignored counts as covered
    assert body["in_progress"] == 2
    assert sorted(body["in_progress_words"]) == ["中文", "喜欢"]
    assert body["with_progress_pct"] == 1.0
    assert body["to_unlock"] == 0


def test_to_unlock_takes_the_most_frequent_missing_words_first():
    counts = readability.WordCounts()
    for w in ["的"] * 10 + ["是"] * 85 + ["猫"] * 3 + ["狗"] * 2:
        counts.add(w)
    summary = readability.summarize(counts, {"是": "known"})
    # 85 % known; 的 (10 occurrences) alone lifts it to 95 %.
    assert summary.to_unlock == 1
    assert readability.summarize(counts, {"是": "known", "的": "known"}).unlocked


def test_an_empty_text_is_readable(words_client):
    body = _post(words_client, ["。", "abc"])
    assert body["total"] == 0 and body["unlocked"] is True and body["to_unlock"] == 0


def test_classify_thresholds():
    assert readability.classify("learning", 1.0) == "known"
    assert readability.classify("learning", 0.99) == "in_progress"
    assert readability.classify("known", None) == "known"
