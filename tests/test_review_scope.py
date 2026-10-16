"""Review sessions focused on one text or one vocab list."""

import json

from app.database import UserWord, VocabularyList
from tests.test_user_words import words_client as _words_client

words_client = _words_client

TOKENS = ["我", "喜欢", "看书", "。", "道", "可", "道", "。"]


def _prelearn(client, words, key="text:abc-8", glosses=None):
    r = client.post(
        "/api/readability/prelearn",
        json={
            "tokens": TOKENS,
            "words": words,
            "text_key": key,
            "title": "Dao 1",
            "glosses": glosses or {},
        },
    )
    assert r.status_code == 200, r.text


def _queue(client, **params):
    r = client.get("/api/review/queue", params={"mode": "mixed", **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_text_session_serves_only_that_texts_words(words_client):
    words_client.post("/api/words/state", json={"word": "中文", "state": "learning"})
    _prelearn(words_client, ["看书", "喜欢"])
    _prelearn(words_client, ["我"], key="text:other-1")
    body = _queue(words_client, text_key="text:abc-8")
    assert sorted(c["word"] for c in body["cards"]) == ["喜欢", "看书"]
    assert body["scope_title"] == "Dao 1"
    # The unfocused queue still has everything.
    assert {"中文", "喜欢", "看书", "我"} <= {c["word"] for c in _queue(words_client)["cards"]}


def test_a_text_session_leads_with_the_texts_meaning(words_client):
    tag = "Dao De Jing"
    _prelearn(
        words_client,
        ["道"],
        glosses={"道": {"meaning": "the Tao", "source": "package", "tag": tag}},
    )
    card = _queue(words_client, text_key="text:abc-8")["cards"][0]
    assert card["focus_gloss"]["meaning"] == "the Tao"
    assert card["focus_gloss"]["tag"] == tag
    # Outside the focused session there is no focus, but the gloss is listed.
    plain = next(c for c in _queue(words_client)["cards"] if c["word"] == "道")
    assert plain["focus_gloss"] is None
    assert any(g["meaning"] == "the Tao" for g in plain["glosses"])


def test_a_focused_session_enrols_no_new_words(words_client):
    s = words_client.session_factory()
    from app.database import User

    s.query(User).filter(User.id == 1).update({"daily_new_words": 5})
    s.commit()
    s.close()
    _prelearn(words_client, ["看书"])
    _queue(words_client, text_key="text:abc-8")
    s = words_client.session_factory()
    assert s.query(UserWord).count() == 1
    s.close()


def test_stats_count_the_scope(words_client):
    _prelearn(words_client, ["看书", "喜欢"])
    stats = words_client.get("/api/review/stats", params={"text_key": "text:abc-8"}).json()
    assert stats["scope"] == {
        "title": "Dao 1",
        "due": 2,
        "total": 2,
        "due_now": 2,
        "due_today": 2,
        "learned": 0,
    }
    assert words_client.get("/api/review/stats").json()["scope"] is None


def test_stats_count_learned_words_of_the_scope(words_client):
    _prelearn(words_client, ["看书", "喜欢"])
    s = words_client.session_factory()
    s.query(UserWord).filter(UserWord.word == "看书").update({"stability": 3.0})
    s.commit()
    s.close()
    stats = words_client.get("/api/review/stats", params={"text_key": "text:abc-8"}).json()
    assert stats["scope"]["learned"] == 1


def _make_list(client):
    s = client.session_factory()
    sections = [
        {
            "name": "Ch1",
            "words": [
                {"hanzi": "道", "meaning": "the Way (Dao)"},
                {"hanzi": "看书", "meaning": ""},
            ],
        },
        {"name": "Ch2", "words": [{"hanzi": "喜欢", "meaning": "to delight in"}]},
    ]
    vl = VocabularyList(
        user_id=1, name="Dao list", list_type="custom", sections=json.dumps(sections)
    )
    s.add(vl)
    s.commit()
    list_id = vl.id
    s.close()
    return list_id


def test_learn_a_list_and_review_it_with_its_meanings(words_client):
    list_id = _make_list(words_client)
    words_client.post("/api/words/state", json={"word": "喜欢", "state": "known"})
    r = words_client.post(f"/api/vocabulary-lists/{list_id}/learn", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(body["added"]) == ["看书", "道"]
    assert body["already_tracked"] == 1
    s = words_client.session_factory()
    assert s.query(UserWord).filter(UserWord.word == "喜欢").one().state == "known"
    s.close()

    cards = {c["word"]: c for c in _queue(words_client, list_id=list_id)["cards"]}
    assert set(cards) == {"道", "看书"}  # 喜欢 is known and not due
    assert cards["道"]["focus_gloss"]["meaning"] == "the Way (Dao)"
    assert cards["道"]["focus_gloss"]["tag"] == "Dao list"
    assert cards["看书"]["focus_gloss"] is None
    stats = words_client.get("/api/review/stats", params={"list_id": list_id}).json()
    assert stats["scope"]["title"] == "Dao list"
    assert stats["scope"]["total"] == 3


def test_learn_one_section(words_client):
    list_id = _make_list(words_client)
    body = words_client.post(
        f"/api/vocabulary-lists/{list_id}/learn", json={"section_name": "Ch2"}
    ).json()
    assert body["added"] == ["喜欢"]


def test_another_users_list_is_not_found(words_client):
    s = words_client.session_factory()
    vl = VocabularyList(user_id=2, name="Bob", list_type="custom", sections="[]")
    s.add(vl)
    s.commit()
    list_id = vl.id
    s.close()
    assert words_client.post(f"/api/vocabulary-lists/{list_id}/learn", json={}).status_code == 404
    assert words_client.get("/api/review/queue", params={"list_id": list_id}).status_code == 404
