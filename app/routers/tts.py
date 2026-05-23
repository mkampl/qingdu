from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.tts import fetch_chinese_tts

router = APIRouter(tags=["TTS"])


class SentenceTtsRequest(BaseModel):
    text: str


@router.get("/api/tts/{text}")
async def text_to_speech(text: str):
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
async def sentence_to_speech(payload: SentenceTtsRequest):
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
