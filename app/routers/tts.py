from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.tts import fetch_chinese_tts

router = APIRouter(tags=["TTS"])


@router.get("/api/tts/{text}")
async def text_to_speech(text: str):
    """Text-to-speech proxy for Google Translate TTS."""
    try:
        audio = await fetch_chinese_tts(text)
        return Response(
            content=audio,
            media_type="audio/mpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {e!s}") from e
