"""Shared slowapi limiter — import from routers to apply rate limits."""

from slowapi import Limiter
from starlette.requests import Request


def client_ip(request: Request) -> str:
    """The client address every per-IP limit is keyed on.

    Never parses X-Forwarded-For itself: uvicorn's proxy-headers handling
    already rewrites `request.client` from that header when the peer is
    listed in FORWARDED_ALLOW_IPS (see Dockerfile / .env.example). Reading
    the raw header here would let anyone who reaches the port directly
    pick their own key."""
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip)
