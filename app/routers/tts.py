import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.constants import MAX_TTS_CHARS
from app.core.rate_limit import limiter
from app.services.tts import fetch_chinese_tts

router = APIRouter(tags=["TTS"])
logger = logging.getLogger(__name__)

# These anonymous endpoints proxy Google's public TTS service. 60/min per
# IP is generous for real reading (the narration player requests sentence
# by sentence) while keeping them from serving as an open proxy.
TTS_RATE_LIMIT = "60/minute"

# Both endpoints are anonymous, so upstream errors (hostnames, status
# lines, exception text) stay in the server log.
_TTS_FAILED = "Text-to-speech is unavailable right now."


class SentenceTtsRequest(BaseModel):
    text: str


async def _speak(text: str) -> Response:
    try:
        audio = await fetch_chinese_tts(text)
    except Exception:
        logger.exception("TTS failed for %d chars", len(text))
        raise HTTPException(status_code=502, detail=_TTS_FAILED) from None
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/api/tts/{text}")
@limiter.limit(TTS_RATE_LIMIT)
async def text_to_speech(request: Request, text: str):
    """Text-to-speech proxy for short text (word level). URL-path based."""
    if len(text) > MAX_TTS_CHARS:
        raise HTTPException(status_code=413, detail="Text is too long for text-to-speech.")
    return await _speak(text)


@router.post("/api/tts/sentence")
@limiter.limit(TTS_RATE_LIMIT)
async def sentence_to_speech(request: Request, payload: SentenceTtsRequest):
    """
    TTS for sentence-length text. Body-based so we don't hit URL-path
    length limits, and the service layer transparently chunks anything
    over Google's ~200-char cap before concatenating the MP3 frames.

    Used by the continuous-narration player and the sentence-translation
    chip in the reader.
    """
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > MAX_TTS_CHARS:
        raise HTTPException(status_code=413, detail="Text is too long for text-to-speech.")
    return await _speak(text)
