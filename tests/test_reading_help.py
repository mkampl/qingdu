"""LLM reading help: comprehension questions for saved texts and the
meaning of a word in its sentence."""

import json

from app.database import SavedText
from app.services import word_sense
from app.state import hsk_vocab

QUESTIONS = {
    "questions": [
        {
            "question": "Where does Xiao Ming go?",
            "correct": "To school",
            "wrong": ["Home", "To the park", "To work"],
        },
        {
            "question": "When?",
            "correct": "In the morning",
            "wrong": ["At night", "At noon", "In the morning"],
        },
        {"question": "How?", "correct": "By bike", "wrong": ["On foot", "By bus", "By car"]},
        {
            "question": "With whom?",
            "correct": "Alone",
            "wrong": ["With friends", "With his mother"],
        },
        {
            "question": "Why?",
            "correct": "He has class",
            "wrong": ["He is hungry", "It rains", "He is late"],
        },
    ]
}


def _text(client, content="小明早上骑自行车去学校。", text_id=1):
    s = client.session_factory()
    s.add(SavedText(id=text_id, user_id=1, title="t", content=content, analysis_data="{}"))
    s.commit()
    s.close()


def test_questions_are_written_graded_and_keep_the_key_on_the_server(words_client, fake_llm):
    _text(words_client)
    assert words_client.get("/api/texts/1/quiz").json() == {"questions": []}
    fake_llm.append(json.dumps(QUESTIONS))
    body = words_client.post("/api/texts/1/quiz/write").json()
    # Questions with fewer than three distinct wrong answers are left out.
    assert len(body["questions"]) == 3
    assert all(
        set(q) == {"prompt", "options"} and len(q["options"]) == 4 for q in body["questions"]
    )
    assert words_client.get("/api/texts/1/quiz").json() == body

    right = [
        q["options"].index(c)
        for q, c in zip(
            body["questions"],
            ["To school", "By bike", "He has class"],
            strict=True,
        )
    ]
    wrong = [(right[0] + 1) % 4, *right[1:]]
    r = words_client.post("/api/texts/1/quiz", json={"answers": wrong}).json()
    assert r == {"results": [False, True, True], "all_correct": False}
    r = words_client.post("/api/texts/1/quiz", json={"answers": right}).json()
    assert r["all_correct"]
    s = words_client.session_factory()
    assert s.get(SavedText, 1).reading_progress == 1.0  # counts as read
    s.close()


def test_an_edited_text_has_no_questions(words_client, fake_llm):
    _text(words_client)
    fake_llm.append(json.dumps(QUESTIONS))
    words_client.post("/api/texts/1/quiz/write")
    words_client.patch("/api/texts/1", json={"content": "完全不同的文章。"})
    assert words_client.get("/api/texts/1/quiz").json() == {"questions": []}
    assert words_client.post("/api/texts/1/quiz", json={"answers": [0]}).status_code == 404


def test_word_sense_keeps_only_the_dictionarys_readings(words_client, fake_llm, monkeypatch):
    monkeypatch.setitem(
        hsk_vocab,
        "行",
        {
            "pinyin": "xíng",
            "meaning": "to walk",
            "readings": [
                {"pinyin": "xíng", "is_main": True, "meanings": ["to walk", "OK"]},
                {"pinyin": "háng", "is_main": False, "meanings": ["row", "profession"]},
            ],
        },
    )
    word_sense._cache.clear()
    fake_llm.append(
        json.dumps({"meaning": "line of business", "sense": 4, "pinyin": "hang2", "note": ""})
    )
    r = words_client.post(
        "/api/words/sense", json={"word": "行", "sentence": "他干这一行十年了。"}
    ).json()
    assert r == {
        "word": "行",
        "meaning": "line of business",
        "pinyin": "háng",
        "dictionary_sense": "profession",
        "note": None,
    }
    fake_llm.append(json.dumps({"meaning": "OK", "sense": 9, "pinyin": "xing4"}))
    r = words_client.post(
        "/api/words/sense", json={"word": "行", "sentence": "行，就这样。"}
    ).json()
    assert r["dictionary_sense"] is None and r["pinyin"] is None  # no such sense, no such reading
    bad = words_client.post("/api/words/sense", json={"word": "猫", "sentence": "行，就这样。"})
    assert bad.status_code == 422


def test_reading_help_is_off_without_an_llm(words_client):
    _text(words_client)
    assert words_client.post("/api/texts/1/quiz/write").status_code == 503
    assert (
        words_client.post("/api/words/sense", json={"word": "行", "sentence": "行。"}).status_code
        == 503
    )
