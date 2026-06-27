"""
Phase 2.7 — Math captcha for open registration.

Lightweight, F-Droid-clean (no external script, no third-party API). The
server issues a one-shot JWT carrying the expected answer; the client
sends the answer back with the registration request and the server
verifies the JWT signature + answer match.

A captcha is single-use only in the sense that it expires fast (90 s)
and a fresh JWT is required for each `POST /api/auth/register`. The
JWT itself is stateless — no DB row needed.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from jose import JWTError, jwt

from app.auth import ALGORITHM, SECRET_KEY

CAPTCHA_TTL_SECONDS = 90


def issue() -> dict[str, str]:
    """Return a (question, token) pair. The token is a JWT carrying the
    expected answer, signed with the instance SECRET_KEY."""
    a = random.randint(2, 9)
    b = random.randint(2, 9)
    op = random.choice(["+", "-"])
    if op == "-":
        # Order so the result is non-negative — keeps the answer in the
        # 0..9 single-digit band, easier on humans and harder for the
        # bot-checker to silently coerce signs.
        a, b = max(a, b), min(a, b)
        answer = a - b
    else:
        answer = a + b
    expire = datetime.utcnow() + timedelta(seconds=CAPTCHA_TTL_SECONDS)
    token = jwt.encode(
        {"a": answer, "exp": expire, "kind": "captcha"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return {"question": f"{a} {op} {b}", "token": token}


def verify(token: str, answer: int | str) -> bool:
    """True iff the token is a valid (unexpired, correctly-signed) captcha
    JWT *and* `answer` matches the bound value. Any decode error → False
    so we never leak which gate failed."""
    if not token or answer is None:
        return False
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return False
    if payload.get("kind") != "captcha":
        return False
    try:
        expected = int(payload.get("a"))
        given = int(answer)
    except (TypeError, ValueError):
        return False
    return expected == given
