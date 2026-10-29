"""
Watch and read: fetch a YouTube video's Chinese caption track and run it
through the reader's segmentation/HSK pipeline, so the frontend can show
a synced, clickable transcript next to the embedded video.

Results are cached in a small per-process LRU: a video's captions do not
change, and YouTube's caption endpoint rate-limits or blocks some
datacenter IPs, so a repeat view should not fetch again.
"""

from __future__ import annotations

import asyncio
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


async def _analyze_segments(sentences: list) -> list[YoutubeSegment]:
    """One analyze_chinese_text() call for the whole video: the sentences
    are joined with '\\n' and the result is split back at the linebreak
    tokens."""
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
        # Blocking HTTP to YouTube — keep it off the event loop.
        sentences, is_generated = await asyncio.to_thread(fetch_captioned_sentences, video_id)
    except YoutubeCaptionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    logger.info(
        "Fetched %d caption sentences for %s (auto-generated=%s)",
        len(sentences),
        video_id,
        is_generated,
    )
    segments = await _analyze_segments(sentences)
    response = YoutubeReadResponse(video_id=video_id, is_generated=is_generated, segments=segments)
    _cache_put(video_id, response)
    return response
