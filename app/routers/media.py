"""
Watch-and-read prototype (spike, not a shipped feature yet).

Given a YouTube URL, fetch its Chinese caption track and run it through
the same word-segmentation/HSK-lookup pipeline the Reader already uses,
so the frontend can render a synced, clickable transcript next to the
embedded video — the same interaction TeaTime Chinese offers with its own
proprietary transcripts, built here on openly-available caption data
instead. See the companion write-up for the licensing/feasibility
analysis behind this.

Caching is a plain in-memory dict: a video's captions never change, and
every fetch either hits YouTube's public caption endpoint (which has been
observed rate-limiting/blocking requests from some datacenter IPs) or
re-runs analysis on every sentence, so a repeat view of the same video
should cost nothing. Fine for a single-process prototype; would need to
move to the database (like the rest of the app's persistent state) if
this graduates into a real feature.
"""

from __future__ import annotations

import logging
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_auth
from app.database import User
from app.schemas import WordInfo
from app.services.segmentation import analyze_chinese_text
from app.services.youtube_captions import (
    YoutubeCaptionError,
    extract_video_id,
    fetch_captioned_sentences,
)

router = APIRouter(tags=["Watch & Read (prototype)"])
logger = logging.getLogger(__name__)

_CACHE_MAX = 50
_cache: OrderedDict[str, YoutubeReadResponse] = OrderedDict()


class YoutubeReadRequest(BaseModel):
    url: str


class YoutubeSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[WordInfo]


class YoutubeReadResponse(BaseModel):
    video_id: str
    is_generated: bool
    segments: list[YoutubeSegment]


def _cache_get(video_id: str) -> YoutubeReadResponse | None:
    hit = _cache.get(video_id)
    if hit is not None:
        _cache.move_to_end(video_id)
    return hit


def _cache_put(video_id: str, value: YoutubeReadResponse) -> None:
    _cache[video_id] = value
    _cache.move_to_end(video_id)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


async def _analyze_segments(sentences: list, is_generated: bool) -> list[YoutubeSegment]:
    """
    One analyze_chinese_text() call for the whole video instead of one per
    sentence: joining every sentence with '\\n' and splitting the result
    back up on the linebreak markers it emits is far cheaper than N
    separate calls (each of which would fire its own batch of online
    lookups) and gives every unknown word in the video a single shared
    concurrent-lookup pass instead of N of them.
    """
    combined = "\n".join(s.text for s in sentences)
    result = await analyze_chinese_text(combined)
    words = result["words"]

    segments: list[YoutubeSegment] = []
    current: list[dict] = []
    sentence_iter = iter(sentences)
    sentence = next(sentence_iter, None)
    for word in words:
        if word["text"] == "\n":
            if sentence is not None:
                segments.append(
                    YoutubeSegment(
                        start=sentence.start,
                        end=sentence.end,
                        text=sentence.text,
                        words=[WordInfo(**w) for w in current],
                    )
                )
            current = []
            sentence = next(sentence_iter, None)
            continue
        current.append(word)
    if sentence is not None:
        segments.append(
            YoutubeSegment(
                start=sentence.start,
                end=sentence.end,
                text=sentence.text,
                words=[WordInfo(**w) for w in current],
            )
        )
    return segments


@router.post("/api/media/youtube", response_model=YoutubeReadResponse)
async def read_youtube(
    data: YoutubeReadRequest,
    user: User = Depends(require_auth),
) -> YoutubeReadResponse:
    """Fetch a YouTube video's Chinese captions, analyzed for the reader."""
    _ = user  # auth-gated so this isn't a free YouTube-fetch proxy for the world
    try:
        video_id = extract_video_id(data.url)
    except YoutubeCaptionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cached = _cache_get(video_id)
    if cached is not None:
        return cached

    try:
        sentences, is_generated = fetch_captioned_sentences(video_id)
    except YoutubeCaptionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    logger.info(
        "Fetched %d caption sentences for %s (auto-generated=%s)",
        len(sentences),
        video_id,
        is_generated,
    )
    segments = await _analyze_segments(sentences, is_generated)
    response = YoutubeReadResponse(video_id=video_id, is_generated=is_generated, segments=segments)
    _cache_put(video_id, response)
    return response
