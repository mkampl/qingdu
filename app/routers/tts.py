from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.rate_limit import limiter
from app.services.tts import fetch_chinese_tts

router = APIRouter(tags=["TTS"])

# These endpoints proxy to Google's public TTS service and were shipped
# with NO rate limit at all — an anonymous open proxy. 60/min per IP is
# generous for real reading (the narration player requests sentence by
# sentence) while capping abuse.
TTS_RATE_LIMIT = "60/minute"


class SentenceTtsRequest(BaseModel):
    text: str


@router.get("/api/tts/{text}")
@limiter.limit(TTS_RATE_LIMIT)
async def text_to_speech(request: Request, text: str):
    """Text-to-speech proxy for short text (word level). URL-path based."""
    try:
        audio = await fetch_chinese_tts(text)
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {e!s}") from e


@router.post("/api/tts/sentence")
@limiter.limit(TTS_RATE_LIMIT)
async def sentence_to_speech(request: Request, payload: SentenceTtsRequest):
    """
    TTS for sentence-length text. Body-based so we don't hit URL-path
    length limits, and the service layer transparently chunks anything
    over Google's ~200-char cap before concatenating the MP3 frames.

    Used by the continuous-narration player in the reader.
    """
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    try:
        audio = await fetch_chinese_tts(text)
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {e!s}") from e
