from fastapi import APIRouter

from app.state import hsk_vocab

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
    }
