import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.core.constants import (
    MAX_TRANSLATE_CHARS,
    TRANSLATE_RATE_LIMIT,
    TRANSLATION_SOURCE_CACHE,
)
from app.core.rate_limit import limiter
from app.database import User, get_db
from app.routers.analyze import _build_glossary
from app.schemas import TranslationRequest
from app.services.translation import get_translation_with_source, translation_cache

router = APIRouter(tags=["Translation"])


@router.post("/api/translate")
@limiter.limit(TRANSLATE_RATE_LIMIT)
async def translate_text(
    request: Request,
    data: TranslationRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Translate Chinese text to a target language."""
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")
    if len(text) > MAX_TRANSLATE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Text is too long — the limit is {MAX_TRANSLATE_CHARS:,} characters.",
        )

    # Glossary terms in the text (longest first, two characters or more:
    # a single character is far more often an everyday word).
    glossary = _build_glossary(db, user, data.glossary_list_ids, flagged_only=False)
    terms, rest = [], text
    for zh in sorted(glossary, key=len, reverse=True):
        if len(zh) > 1 and zh in rest and glossary[zh].get("meaning"):
            terms.append((zh, glossary[zh]["meaning"]))
            rest = rest.replace(zh, "")
        if len(terms) >= 12:
            break

    cache_key = f"{text}_{data.target_lang}"
    if terms:
        digest = hashlib.sha1(repr(terms).encode("utf-8")).hexdigest()[:12]
        cache_key += f"_{digest}"
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

    translation_result = await get_translation_with_source(text, terms)
    if not translation_result:
        raise HTTPException(status_code=500, detail="All translation services failed")

    translation_cache[cache_key] = translation_result
    return {
        "translation": translation_result["translation"],
        "source": translation_result["source"],
        "cached": False,
    }
