"""Topic series: folder, writing a text with a checked number of new words,
saving it with its translations."""

import asyncio
import json

import httpx
import pytest

from app.database import SavedText, TextFolder, User
from app.services import llm, text_series
from tests.test_user_words import words_client as _words_client

words_client = _words_client

TEXT = {
    "title": "去公园",
    "summary": "Xiao Ming goes to the park.",
    "sentences": [
        {"zh": "今天天气很好。", "en": "The weather is good today."},
        {"zh": "小明去**公园**。", "en": "Xiao Ming goes to the park."},
        {"zh": "公园里有很多人。", "en": "There are many people in the park."},
    ],
    "new_words": ["公园"],
}


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


def _series(client, new_words=3):
    s = client.session_factory()
    user = s.get(User, 1)
    series = text_series.create(s, user, "公园", 1, new_words, "short")
    return s, series


def test_a_series_gets_its_folder(words_client):
    s, series = _series(words_client)
    folder = s.get(TextFolder, series.folder_id)
    assert folder.name == "公园"
    assert s.get(TextFolder, folder.parent_id).name == text_series.PARENT_FOLDER
    s.close()


def test_writing_and_saving_a_text(words_client, fake_llm):
    fake_llm.append(json.dumps(TEXT))
    s, series = _series(words_client)
    written = asyncio.run(text_series._write(s, series))
    assert written["text"].startswith("今天天气很好。")
    assert written["new"]  # nothing is known in a fresh account
    text = asyncio.run(text_series._save(s, series, written))
    data = json.loads(text.analysis_data)
    assert text.folder_id == series.folder_id and text.title == "去公园"
    assert data["sentence_translations"]["小明去公园。"] == "Xiao Ming goes to the park."
    assert data["series"]["summary"] == "Xiao Ming goes to the park."
    assert text_series.payload(s, series)["texts"] == 1
    s.close()


def test_a_text_far_off_the_new_word_target_is_written_again(words_client, fake_llm):
    long_text = dict(TEXT, sentences=TEXT["sentences"] * 1)
    fake_llm += [json.dumps(long_text), json.dumps(TEXT)]
    s, series = _series(words_client, new_words=40)  # 40 wanted, the text has few
    asyncio.run(text_series._write(s, series))
    assert fake_llm == []  # both answers used: the first was off target
    s.close()


def test_endpoints_need_an_llm(words_client, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    llm.reset()
    r = words_client.post("/api/series", json={"topic": "公园"})
    assert r.status_code == 503
    assert words_client.get("/api/series").json() == []
    s = words_client.session_factory()
    assert s.query(SavedText).count() == 0
    s.close()
