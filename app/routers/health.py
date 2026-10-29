from fastapi import APIRouter

from app.state import cedict_vocab, hsk_vocab

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    summary="Health check",
    description="Check if the application is running and vocabulary is loaded",
    response_description="Health status",
)
async def health_check():
    return {
        "status": "healthy",
        "vocab_loaded": len(hsk_vocab) > 0,
        "vocab_count": len(hsk_vocab),
        # Zero means CC-CEDICT failed to load; analyze and review still
        # work on HSK alone, with less polished meanings.
        "cedict_loaded": len(cedict_vocab) > 0,
        "cedict_count": len(cedict_vocab),
    }
