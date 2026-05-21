from typing import Dict

from fastapi import APIRouter, HTTPException, Request

from app.core.constants import ANALYZE_RATE_LIMIT
from app.core.rate_limit import limiter
from app.schemas import TextAnalysisRequest
from app.services.segmentation import analyze_chinese_text
from app.state import hsk_vocab

router = APIRouter(tags=["Analysis"])


@router.post(
    "/api/analyze",
    summary="Analyze Chinese text",
    description=(
        "Analyzes Chinese text and returns HSK level information for each word, "
        "including pinyin, meaning, and statistics."
    ),
    response_description="Analysis results with word-by-word breakdown and statistics",
    responses={
        200: {
            "description": "Successful analysis",
            "content": {
                "application/json": {
                    "example": {
                        "words": [
                            {
                                "text": "你好",
                                "hsk_level": "new-1",
                                "pinyin": "nǐ hǎo",
                                "meaning": "hello",
                                "is_hsk": True,
                                "translation_source": "hsk",
                            }
                        ],
                        "statistics": {
                            "total_characters": 2,
                            "total_words": 1,
                            "hsk_words": 1,
                            "hsk_distribution": {"hsk1": 1},
                            "estimated_level": "HSK 1",
                        },
                    }
                }
            },
        },
        503: {"description": "Vocabulary not loaded yet"},
        400: {"description": "Empty text provided"},
        429: {"description": "Rate limit exceeded (30 requests/minute)"},
    },
)
@limiter.limit(ANALYZE_RATE_LIMIT)
async def analyze_text(request: Request, data: TextAnalysisRequest) -> Dict:
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")

    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")

    return await analyze_chinese_text(text)
