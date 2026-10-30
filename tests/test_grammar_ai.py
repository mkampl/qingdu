"""LLM grammar help: explaining a sentence and writing a practice text."""

import asyncio
import json

from app.services import grammar_ai, llm


def test_explain_keeps_only_offered_points_with_real_spans(fake_llm):
    fake_llm.append(
        json.dumps(
            {
                "points": [
                    {"id": "hsk30-184", "span": "把书放在桌子上"},
                    {"id": "hsk30-999", "span": "把书"},
                    {"id": "hsk30-021", "span": "吃了"},
                ],
                "breakdown": "他 is the subject; 把 moves 书 before the verb.",
                "literal": "he BA book put at table on LE",
            }
        )
    )
    out = asyncio.run(grammar_ai.explain("他把书放在桌子上了。"))
    assert [p["id"] for p in out["points"]] == ["hsk30-184"]
    assert out["breakdown"].startswith("他")
    # Every quoted Chinese word comes with its pinyin.
    assert {"text": "他", "pinyin": "tā"} in out["breakdown_parts"]
    assert "".join(p["text"] for p in out["breakdown_parts"]) == out["breakdown"]
    # Cached: no second request needed.
    assert asyncio.run(grammar_ai.explain("他把书放在桌子上了。")) is out


def test_practice_text_must_use_the_point(words_client, fake_llm):
    fake_llm += [
        json.dumps({"title": "没有", "text": "我很好。"}),  # no 把 at all
        json.dumps({"title": "搬家", "text": "我把书放好了。他把桌子搬走了。"}),
    ]
    s = words_client.session_factory()
    out = asyncio.run(grammar_ai.practice_text(s, 1, "hsk30-184"))
    s.close()
    assert out["title"] == "搬家" and out["text"].count("把") == 2
    assert 0 <= out["known_pct"] <= 1


def test_endpoints_are_off_without_an_llm(words_client, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    llm.reset()
    assert words_client.post("/api/grammar/explain", json={"sentence": "你好。"}).status_code == 503
    assert words_client.post("/api/grammar/hsk30-184/text").status_code == 503
