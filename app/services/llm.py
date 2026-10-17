"""Optional LLM backend (any OpenAI-compatible chat endpoint).

Off unless LLM_BASE_URL and LLM_MODEL are set. Ollama, vLLM, llama.cpp
server, LM Studio and hosted APIs all speak `/v1/chat/completions`.

    LLM_BASE_URL      e.g. http://ollama:11434/v1 or http://vllm:8000/v1
    LLM_MODEL         model name as the server knows it
    LLM_API_KEY       optional bearer token
    LLM_TIMEOUT       seconds per request (default 60)
    LLM_MAX_TOKENS    cap per request (default 1500)
    LLM_TEMPERATURE   default 0.4
    LLM_EXTRA_BODY    JSON merged into every request body, for
                      server-specific switches, e.g. to turn off reasoning:
                      {"chat_template_kwargs": {"enable_thinking": false}}
    LLM_CONCURRENCY   requests at a time per worker (default 1)
    LLM_DAILY_LIMIT   requests per user per day (default 50, 0 = no limit)
    LLM_FEATURES      comma list of features to offer, or "all" (default)

The server checks the endpoint at start and every few minutes (`probe`);
features are offered only while it answers. `capabilities()` is what
GET /api/capabilities reports, so an app switching servers can tell what
each one offers. Nothing here is required: without the variables every
LLM feature is simply off.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import LlmUsage

logger = logging.getLogger(__name__)

# Every LLM feature the app knows; LLM_FEATURES picks from these. Features
# add their name here when they are built.
FEATURES: tuple[str, ...] = ("grammar",)
PROBE_INTERVAL_S = 300
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


class LlmError(Exception):
    """The LLM is off, unreachable, or gave an unusable answer."""


@dataclass
class Config:
    base_url: str
    model: str
    api_key: str | None = None
    timeout: float = 60.0
    max_tokens: int = 1500
    temperature: float = 0.4
    extra_body: dict = field(default_factory=dict)
    concurrency: int = 1
    daily_limit: int = 50
    features: tuple[str, ...] = FEATURES


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        logger.warning("%s is not a number; using %s", name, default)
        return default


def load_config() -> Config | None:
    base_url = (os.getenv("LLM_BASE_URL") or "").strip().rstrip("/")
    model = (os.getenv("LLM_MODEL") or "").strip()
    if not base_url or not model:
        return None
    try:
        extra = json.loads(os.getenv("LLM_EXTRA_BODY") or "{}")
        if not isinstance(extra, dict):
            raise ValueError("not an object")
    except ValueError as e:
        logger.warning("LLM_EXTRA_BODY ignored: %s", e)
        extra = {}
    raw_features = (os.getenv("LLM_FEATURES") or "all").strip()
    features = (
        FEATURES
        if raw_features in ("", "all")
        else tuple(f for f in (x.strip() for x in raw_features.split(",")) if f in FEATURES)
    )
    return Config(
        base_url=base_url,
        model=model,
        api_key=(os.getenv("LLM_API_KEY") or "").strip() or None,
        timeout=_env_float("LLM_TIMEOUT", 60.0),
        max_tokens=int(_env_float("LLM_MAX_TOKENS", 1500)),
        temperature=_env_float("LLM_TEMPERATURE", 0.4),
        extra_body=extra,
        concurrency=max(1, int(_env_float("LLM_CONCURRENCY", 1))),
        daily_limit=max(0, int(_env_float("LLM_DAILY_LIMIT", 50))),
        features=features,
    )


@dataclass
class Status:
    available: bool = False
    checked_at: float | None = None
    latency_ms: int | None = None
    error: str | None = None


_config: Config | None = None
_config_loaded = False
_status = Status()
_semaphore: asyncio.Semaphore | None = None


def config() -> Config | None:
    global _config, _config_loaded
    if not _config_loaded:
        _config = load_config()
        _config_loaded = True
    return _config


def reset() -> None:
    """Forget config and status (tests, or after the environment changed)."""
    global _config, _config_loaded, _status, _semaphore
    _config, _config_loaded, _status, _semaphore = None, False, Status(), None


def status() -> Status:
    return _status


def _headers(cfg: Config) -> dict:
    h = {"Content-Type": "application/json"}
    if cfg.api_key:
        h["Authorization"] = f"Bearer {cfg.api_key}"
    return h


def _strip_reasoning(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def _parse_json(text: str) -> dict:
    """The JSON object in a reply; tolerates a ```json fence."""
    text = _strip_reasoning(text)
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LlmError("The model's answer is not JSON")
    try:
        data = json.loads(text[start : end + 1])
    except ValueError as e:
        raise LlmError("The model's answer is not valid JSON") from e
    if not isinstance(data, dict):
        raise LlmError("The model's answer is not a JSON object")
    return data


async def chat(
    messages: list[dict],
    *,
    schema: dict | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
) -> str | dict:
    """One chat completion. With `schema` the model is asked for JSON of
    that shape and the parsed object is returned; otherwise the text."""
    global _semaphore
    cfg = config()
    if cfg is None:
        raise LlmError("No LLM is configured on this server")
    body: dict = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens or cfg.max_tokens,
        "temperature": cfg.temperature if temperature is None else temperature,
        **cfg.extra_body,
    }
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "answer", "schema": schema},
        }
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(cfg.concurrency)
    async with _semaphore:
        try:
            async with httpx.AsyncClient(timeout=timeout or cfg.timeout) as client:
                r = await client.post(
                    f"{cfg.base_url}/chat/completions", headers=_headers(cfg), json=body
                )
        except httpx.HTTPError as e:
            raise LlmError(f"The LLM did not answer ({type(e).__name__})") from e
    if r.status_code != 200:
        raise LlmError(f"The LLM answered {r.status_code}")
    try:
        content = r.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LlmError("Unexpected answer from the LLM") from e
    return _parse_json(content) if schema is not None else _strip_reasoning(content)


async def probe() -> Status:
    """Check the configured endpoint with a tiny JSON request."""
    global _status
    cfg = config()
    if cfg is None:
        _status = Status(available=False, checked_at=time.time(), error="not configured")
        return _status
    started = time.monotonic()
    try:
        reply = await chat(
            [
                {
                    "role": "user",
                    "content": 'Reply with the JSON object {"ok": true} and nothing else.',
                }
            ],
            schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
            },
            max_tokens=20,
            temperature=0,
            timeout=min(cfg.timeout, 30),
        )
        ok = isinstance(reply, dict) and reply.get("ok") is True
        _status = Status(
            available=ok,
            checked_at=time.time(),
            latency_ms=int((time.monotonic() - started) * 1000),
            error=None if ok else "unexpected probe answer",
        )
    except LlmError as e:
        _status = Status(available=False, checked_at=time.time(), error=str(e))
    if _status.available:
        logger.info("LLM %s available (%d ms)", cfg.model, _status.latency_ms)
    else:
        logger.warning("LLM %s unavailable: %s", cfg.model, _status.error)
    return _status


def enabled(feature: str) -> bool:
    cfg = config()
    return bool(cfg and _status.available and feature in cfg.features)


def capabilities() -> dict:
    """What this server's LLM offers right now (no URL or key)."""
    cfg = config()
    available = bool(cfg and _status.available)
    return {
        "configured": cfg is not None,
        "available": available,
        "model": cfg.model if cfg else None,
        "features": list(cfg.features) if available and cfg else [],
        "daily_limit": cfg.daily_limit if cfg else 0,
    }


def require(feature: str) -> Config:
    """The config, or a 503 the SPA shows as "not available here"."""
    cfg = config()
    if cfg is None or feature not in cfg.features:
        raise HTTPException(status_code=503, detail="This server has no LLM for that")
    if not _status.available:
        raise HTTPException(status_code=503, detail="The LLM is not reachable right now")
    return cfg


def charge(db: Session, user_id: int, today: date | None = None) -> int:
    """Count one LLM request for the user; 429 over the daily limit.
    Returns how many are left today."""
    cfg = config()
    limit = cfg.daily_limit if cfg else 0
    today = today or date.today()
    row = db.query(LlmUsage).filter(LlmUsage.user_id == user_id, LlmUsage.day == today).first()
    used = row.count if row else 0
    if limit and used >= limit:
        raise HTTPException(
            status_code=429, detail=f"Daily limit of {limit} LLM requests reached; try tomorrow"
        )
    if row is None:
        db.add(LlmUsage(user_id=user_id, day=today, count=1))
    else:
        row.count = used + 1
    db.commit()
    return max(0, limit - used - 1) if limit else -1


__all__ = [
    "FEATURES",
    "LlmError",
    "capabilities",
    "charge",
    "chat",
    "config",
    "enabled",
    "probe",
    "require",
    "reset",
    "status",
]
