"""Optional LLM backend: config from the environment, probe, JSON replies,
daily limit, and what /api/capabilities reports."""

import asyncio
import json
from datetime import date

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, User
from app.services import llm


@pytest.fixture
def fake_llm(monkeypatch):
    """An OpenAI-compatible endpoint; `replies` is what it answers next."""
    seen: list[dict] = []
    replies: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        reply = replies.pop(0) if replies else '{"ok": true}'
        if isinstance(reply, int):
            return httpx.Response(reply)
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        llm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1/")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_EXTRA_BODY", '{"chat_template_kwargs": {"enable_thinking": false}}')
    monkeypatch.setenv("LLM_DAILY_LIMIT", "2")
    llm.reset()
    yield seen, replies
    llm.reset()


def test_off_without_configuration(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    llm.reset()
    assert llm.capabilities()["configured"] is False
    assert asyncio.run(llm.probe()).available is False
    with pytest.raises(HTTPException) as e:
        llm.require("anything")
    assert e.value.status_code == 503


def test_probe_and_request_shape(fake_llm):
    seen, _ = fake_llm
    assert asyncio.run(llm.probe()).available is True
    req = seen[0]
    assert req["headers"]["authorization"] == "Bearer secret"
    assert req["body"]["model"] == "test-model"
    assert req["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert req["body"]["response_format"]["type"] == "json_schema"
    caps = llm.capabilities()
    assert caps["available"] and caps["model"] == "test-model"
    assert "llm.test" not in json.dumps(caps) and "secret" not in json.dumps(caps)


def test_replies_lose_reasoning_and_fences(fake_llm):
    _, replies = fake_llm
    replies += ["<think>hmm</think>你好", '<think>x</think>```json\n{"a": 1}\n```']
    assert asyncio.run(llm.chat([{"role": "user", "content": "hi"}])) == "你好"
    assert asyncio.run(llm.chat([{"role": "user", "content": "hi"}], schema={})) == {"a": 1}


def test_an_error_makes_it_unavailable(fake_llm):
    _, replies = fake_llm
    replies.append(500)
    st = asyncio.run(llm.probe())
    assert st.available is False and "500" in st.error


def test_daily_limit(fake_llm):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(User(id=1, username="a", password_hash="x"))
    db.commit()
    day = date(2026, 10, 17)
    assert llm.charge(db, 1, day) == 1
    assert llm.charge(db, 1, day) == 0
    with pytest.raises(HTTPException) as e:
        llm.charge(db, 1, day)
    assert e.value.status_code == 429
    assert llm.charge(db, 1, date(2026, 10, 18)) == 1


def test_capabilities_endpoint(app_module, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    llm.reset()
    with TestClient(app_module) as c:
        body = c.get("/api/capabilities").json()
    assert body["llm"]["available"] is False
    assert "mymemory" in body["translation"]
