from typing import Dict

from fastapi import APIRouter, HTTPException, Request

from app.core.constants import TRANSLATE_RATE_LIMIT, TRANSLATION_SOURCE_CACHE
from app.core.rate_limit import limiter
from app.schemas import TranslationRequest
from app.services.translation import get_translation_with_source, translation_cache

router = APIRouter(tags=["Translation"])


@router.post("/api/translate")
@limiter.limit(TRANSLATE_RATE_LIMIT)
async def translate_text(request: Request, data: TranslationRequest) -> Dict:
    """Translate Chinese text to a target language."""
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")

    cache_key = f"{text}_{data.target_lang}"
    if cache_key in translation_cache:
        cached_result = translation_cache[cache_key]
        # Support both the legacy str cache shape and the current dict shape.
        if isinstance(cached_result, str):
            return {
                "translation": cached_result,
                "source": TRANSLATION_SOURCE_CACHE,
                "cached": True,
            }
        return {
            "translation": cached_result.get("translation", cached_result),
            "source": cached_result.get("source", TRANSLATION_SOURCE_CACHE),
            "cached": True,
        }

    translation_result = await get_translation_with_source(text)
    if not translation_result:
        raise HTTPException(status_code=500, detail="All translation services failed")

    translation_cache[cache_key] = translation_result
    return {
        "translation": translation_result["translation"],
        "source": translation_result["source"],
        "cached": False,
    }
