"""Grammar points of a sentence from the LLM (services/grammar_tagging):
only offered points, spans that are in the sentence, stored per sentence."""

import asyncio
import json

import httpx
import pytest

from app.services import grammar_catalog, grammar_tagging, llm


@pytest.fixture
def fake_llm(monkeypatch):
    replies: list[str] = []
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        content = replies.pop(0) if replies else '{"ok": true}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_MODEL", "m")
    llm.reset()
    asyncio.run(llm.probe())
    yield replies
    llm.reset()


def test_candidates_come_from_the_points_words():
    ids = {c["id"] for c in grammar_catalog.candidates("我把书放在桌子上了。")}
    assert "hsk30-184" in ids  # 把 sentence
    assert all(grammar_catalog.get(i)["markers"] for i in ids)


def test_tags_are_checked(fake_llm):
    sentence = "我把书放在桌子上了。"
    batch = [(grammar_tagging.sentence_hash(sentence), sentence)]
    fake_llm.append(
        json.dumps(
            {
                "sentences": [
                    {
                        "n": 1,
                        "points": [
                            {"id": "hsk30-184", "span": "把书放在桌子上"},
                            {"id": "hsk30-999", "span": "把书"},  # not offered
                            {"id": "hsk30-041", "span": "吃了"},  # span not in the sentence
                        ],
                    }
                ]
            }
        )
    )
    out = asyncio.run(grammar_tagging.tag_batch(batch))
    assert out[batch[0][0]] == [{"id": "hsk30-184", "span": "把书放在桌子上"}]


def test_nothing_is_queued_without_an_llm(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    llm.reset()
    assert grammar_tagging.enqueue(["我把书放在桌子上了。"]) == 0


def test_a_span_must_hold_the_points_word():
    s = "她们买了不少东西，逛到天黑才回宿舍。"
    assert grammar_tagging.span_fits("hsk30-041", "买了", s)
    assert not grammar_tagging.span_fits("hsk30-040", "逛到天黑才回宿舍", s)  # 了2 without 了
    assert not grammar_tagging.span_fits("hsk30-041", "吃了", s)  # not in the sentence


def test_tags_of_an_older_round_are_done_again():
    assert grammar_tagging.tags_version() == grammar_catalog.version() * 100 + grammar_tagging.RULES
