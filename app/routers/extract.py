"""
Server-side article extraction. The user pastes any URL — typically from
one of the sources listed at /discover — and gets back the cleaned-up
article body for analysis, without the chrome of the originating site.

Uses trafilatura because it's the best open-source extractor for
multilingual content (including Chinese) and handles the news/blog
shapes most learners will hit.

SSRF defence: only http/https schemes, never IP literals or hostnames
that resolve into private/loopback/link-local space. Auth-gated so the
endpoint isn't a free internet-egress probe for the world.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import trafilatura
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_auth
from app.database import User

router = APIRouter(tags=["Extract"])
logger = logging.getLogger(__name__)


class ExtractRequest(BaseModel):
    url: str = Field(..., description="Public http(s) URL of an article to extract.")


class ExtractResponse(BaseModel):
    url: str
    title: str | None
    byline: str | None
    excerpt: str | None
    content: str
    char_count: int


def _validate_url(url: str) -> str:
    """Return the URL if it's safe to fetch, else raise HTTPException."""
    try:
        parsed = urlparse(url.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Malformed URL: {e}") from e

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(
            status_code=400,
            detail="Only http and https URLs are allowed.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="URL is missing a hostname.")

    # Block hostnames that already look like raw IPs in private space.
    try:
        ip = ipaddress.ip_address(hostname)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise HTTPException(
                status_code=400,
                detail="Won't fetch internal/private addresses.",
            )
    except ValueError:
        # Not an IP literal — resolve it and check every A/AAAA record.
        try:
            infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except OSError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not resolve {hostname!r}: {e}",
            ) from e
        for info in infos:
            sockaddr = info[4]
            addr = sockaddr[0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{hostname} resolves into a private/internal IP range; refusing to fetch."
                    ),
                ) from None

    return url.strip()


def _extract(url: str) -> ExtractResponse:
    """Fetch the URL and pull out the article body. Caps content size."""
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise HTTPException(
            status_code=502,
            detail="Couldn't fetch that URL — the site might be blocking us or down.",
        )

    # output_format='json' gives metadata too. 'no_fallback' off so we still
    # try generic extraction on sites trafilatura doesn't know.
    extracted = trafilatura.extract(
        downloaded,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not extracted:
        raise HTTPException(
            status_code=422,
            detail="We couldn't find a readable article on that page.",
        )

    import json

    try:
        meta = json.loads(extracted)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Bad extractor output: {e}") from e

    content = (meta.get("text") or "").strip()
    if not content:
        raise HTTPException(
            status_code=422,
            detail="The page loaded but its article body was empty.",
        )

    # Hard cap: ~50k chars is roughly a 30-minute reading session at HSK 4
    # pace — more than any single user-session needs and a sensible memory
    # ceiling for the analyse step downstream.
    MAX_CHARS = 50_000
    if len(content) > MAX_CHARS:
        content = content[:MAX_CHARS] + "…"

    return ExtractResponse(
        url=url,
        title=meta.get("title") or None,
        byline=meta.get("author") or None,
        excerpt=(meta.get("excerpt") or meta.get("description") or "")[:300] or None,
        content=content,
        char_count=len(content),
    )


@router.post("/api/extract", response_model=ExtractResponse)
async def extract_article(
    data: ExtractRequest,
    user: User = Depends(require_auth),
) -> ExtractResponse:
    """Fetch and clean an article from any public URL."""
    _ = user  # auth dependency only
    url = _validate_url(data.url)
    logger.info(f"Extracting article from {url}")
    return _extract(url)
