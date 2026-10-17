"""The grammar section: patterns met in read texts, their sentences,
practice exercises and the practice schedule."""

import json
import random
from datetime import datetime, timedelta

from app.database import SavedText
from app.services import grammar_book
from app.services.segmentation import segment_text
from tests.test_user_words import words_client as _words_client

words_client = _words_client

READ = "我把书放在桌子上了。他被老师批评了。"
UNREAD = "苹果被他吃了。"


def _save(client, content, progress, text_id):
    words = [{"text": t} for t in segment_text(content)]
    s = client.session_factory()
    s.add(
        SavedText(
            id=text_id,
            user_id=1,
            title=f"t{text_id}",
            content=content,
            analysis_data=json.dumps({"words": words}),
            reading_progress=progress,
        )
    )
    s.commit()
    s.close()


def test_met_counts_only_texts_read_to_the_end(words_client):
    _save(words_client, READ, 1.0, 1)
    _save(words_client, UNREAD, 0.3, 2)
    body = words_client.get("/api/grammar").json()
    by_id = {p["id"]: p for p in body["points"]}
    assert by_id["hsk30-184"]["met_texts"] == 1  # 把 sentence
    assert by_id["hsk30-185"]["met_sentences"] == 1  # the unread text's 被 doesn't count
    assert by_id["hsk30-172"]["met_texts"] == 0  # 越……越……
    assert body["read_texts"] == 1
    assert body["analysing"] == 0  # no LLM in the tests


def test_pattern_sentences_come_from_read_texts_first(words_client):
    _save(words_client, READ, 1.0, 1)
    _save(words_client, UNREAD, 0.3, 2)
    # The reader's pattern id leads to its catalog point.
    detail = words_client.get("/api/grammar/bei").json()
    assert detail["id"] == "hsk30-185"
    assert detail["sentences"]["read"][0]["sentence"] == "他被老师批评了。"
    assert detail["sentences"]["saved"][0]["sentence"] == "苹果被他吃了。"
    assert words_client.get("/api/grammar/nope").status_code == 404


def test_practice_builds_gap_and_order_items(words_client):
    _save(words_client, READ, 1.0, 1)
    s = words_client.session_factory()
    body = grammar_book.practice(s, 1, "hsk30-184", random.Random(2))
    s.close()
    first = body["items"][0]
    assert first["type"] == "cloze"
    assert first["choices"][first["answer"]] == "把"
    assert first["before"] + "把" + first["after"] == "我把书放在桌子上了。"
    orders = [i for i in body["items"] if i["type"] == "order"]
    assert orders and all(sorted(o["pieces"]) == sorted(o["answer"]) for o in orders)


def test_practice_rounds_move_the_due_date(words_client):
    now = datetime(2026, 10, 17, 12)
    s = words_client.session_factory()
    p = grammar_book.record(s, 1, "hsk30-184", 4, 5, now)
    assert p["box"] == 1 and p["due_at"].startswith((now + timedelta(days=2)).date().isoformat())
    p = grammar_book.record(s, 1, "ba", 5, 5, now)  # old pattern id: same point
    assert p["box"] == 2
    p = grammar_book.record(s, 1, "hsk30-184", 1, 5, now)
    assert p["box"] == 1
    s.close()
    r = words_client.post("/api/grammar/ba/practice", json={"correct": 3, "total": 4})
    assert r.status_code == 200


def test_the_llm_overrules_a_regex_hit_it_turned_down(words_client, monkeypatch):
    from app.services import grammar_tagging

    _save(words_client, "他把书放在桌子上了。", 1.0, 1)
    sentence = "他把书放在桌子上了。"
    monkeypatch.setattr(grammar_book, "_tags", {grammar_tagging.sentence_hash(sentence): []})
    monkeypatch.setattr(grammar_book, "_tags_checked", 1e18)
    s = words_client.session_factory()
    ids = {h.point_id for h in grammar_book.all_hits(s, 1) if h.sentence == sentence}
    s.close()
    assert "hsk30-184" not in ids  # offered to the LLM, not confirmed


def test_prewarm_caches_every_saved_text_and_the_library(words_client):
    _save(words_client, READ, 1.0, 1)
    grammar_book._texts.clear()
    n = grammar_book.prewarm(words_client.session_factory)
    assert "saved:1" in grammar_book._texts
    assert n == len(grammar_book._texts) > 1  # the library came along
