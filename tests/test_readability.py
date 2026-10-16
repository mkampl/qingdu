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


TOKENS = ["我", "喜欢", "看书", "。", "看书", "很", "有意思", "！"]


def _prelearn(client, words, **extra):
    body = {"tokens": TOKENS, "words": words, "text_key": "library:hsk1_01_school", **extra}
    r = client.post("/api/readability/prelearn", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_prelearn_adds_words_with_the_sentence_from_the_text(words_client):
    body = _prelearn(words_client, ["看书", "喜欢"], title="My text")
    assert body["added"] == ["看书", "喜欢"]
    assert body["in_progress"] == 3  # 看书 ×2 + 喜欢
    assert body["prelearned"] == {"total": 2, "learned": 0}
    s = words_client.session_factory()
    row = s.query(UserWord).filter(UserWord.word == "看书").one()
    assert row.state == "learning"
    assert (row.sample_sentence, row.sample_source) == ("我喜欢看书。", "My text")
    s.close()
    # Coming back later: the progress for this text is still there.
    again = _post(words_client, TOKENS, text_key="library:hsk1_01_school")
    assert again["prelearned"] == {"total": 2, "learned": 0}
    assert "看书" not in [m["word"] for m in again["missing"]]


def test_prelearn_keeps_a_known_word_known_and_skips_nothing_twice(words_client):
    _seed(words_client, 喜欢=("known", 90.0))
    body = _prelearn(words_client, ["喜欢", "喜欢"])
    assert body["added"] == []
    s = words_client.session_factory()
    assert s.query(UserWord).filter(UserWord.word == "喜欢").one().state == "known"
    s.close()
    assert body["prelearned"] == {"total": 1, "learned": 1}


def test_prelearn_stores_the_texts_own_meaning(words_client):
    from app.database import TextWord, UserWordGloss

    _prelearn(
        words_client,
        ["有意思", "看书"],
        glosses={
            "有意思": {"meaning": "the Way of interest", "source": "package", "tag": "dao"},
            "看书": {"meaning": "to study the classics", "source": "glossary", "tag": "Dao list"},
        },
    )
    s = words_client.session_factory()
    glosses = {(g.source, g.source_tag, g.meaning) for g in s.query(UserWordGloss).all()}
    assert ("package", "dao", "the Way of interest") in glosses
    assert ("list", "Dao list", "to study the classics") in glosses
    links = {(t.word, t.gloss_source, t.gloss_tag) for t in s.query(TextWord).all()}
    assert ("有意思", "package", "dao") in links
    assert ("看书", "list", "Dao list") in links
    s.close()


def test_prelearn_rejects_a_bad_text_key(words_client):
    r = words_client.post(
        "/api/readability/prelearn",
        json={"tokens": TOKENS, "words": ["看书"], "text_key": "../etc"},
    )
    assert r.status_code == 422


def test_sentences_split_on_punctuation_and_line_breaks():
    split = readability.sentences(["我", "好", "。", "你", "\n", "他", "好"])
    assert [s for s, _ in split] == ["我好。", "你", "他好"]
    assert readability.sentence_for(split, "他") == "他好"
    assert readability.sentence_for(split, "好") == "我好。"


def test_deleting_the_account_removes_the_text_links(words_client):
    from app.database import TextWord, User
    from app.services import lifecycle

    _prelearn(words_client, ["看书"])
    s = words_client.session_factory()
    lifecycle.purge_user(s, s.query(User).filter(User.id == 1).one())
    s.commit()
    assert s.query(TextWord).count() == 0
    s.close()


def test_a_long_package_source_name_is_kept_as_the_tag(words_client):
    from app.database import UserWordGloss

    tag = "Qingdu reference package · hand-curated glosses, Wang Bi recension"
    _prelearn(
        words_client,
        ["有意思"],
        glosses={"有意思": {"meaning": "wondrous", "source": "package", "tag": tag}},
    )
    s = words_client.session_factory()
    assert s.query(UserWordGloss).filter(UserWordGloss.source == "package").one().source_tag == tag
    s.close()
