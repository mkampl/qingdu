from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.core.constants import ANALYZE_RATE_LIMIT, MAX_ANALYZE_CHARS
from app.core.rate_limit import limiter
from app.database import User, UserWord, get_db
from app.schemas import TextAnalysisRequest
from app.services import word_lists
from app.services.script import to_canonical, to_user_script, user_script
from app.services.segmentation import analyze_chinese_text
from app.services.user_words import user_glosses_map
from app.state import hsk_vocab

router = APIRouter(tags=["Analysis"])


def _user_state_map(db: Session, user: User | None) -> dict[str, str]:
    """Fetch the user's full word-state map. Cheap: a single indexed query."""
    if user is None:
        return {}
    rows = db.query(UserWord.word, UserWord.state).filter(UserWord.user_id == user.id).all()
    return dict(rows)


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
        413: {"description": "Text longer than MAX_ANALYZE_CHARS"},
        429: {"description": "Rate limit exceeded (30 requests/minute)"},
    },
)
@limiter.limit(ANALYZE_RATE_LIMIT)
async def analyze_text(
    request: Request,
    data: TextAnalysisRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if len(data.text) > MAX_ANALYZE_CHARS:
        # Analysis cost grows with the text, and anonymous callers can send it.
        raise HTTPException(
            status_code=413,
            detail=f"Text is too long — the limit is {MAX_ANALYZE_CHARS:,} characters.",
        )
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")

    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")

    # Internal analysis always runs on Simplified — that's what jieba's
    # dict, hsk_vocab, and the user_words table are keyed on. For
    # non-auto users, normalise their input first so segmentation
    # works whether they pasted simp or trad text.
    text_simp = to_canonical(text, user)

    glossary = word_lists.build_glossary(db, user, data.glossary_list_ids)
    result = await analyze_chinese_text(text_simp, glossary=glossary)

    # Enrich words with per-user state when the request is authenticated.
    # Anonymous callers get the response unchanged. Lookup happens against
    # the canonical (simp) text before we convert anything to the user's
    # display script.
    states = _user_state_map(db, user)
    glosses_map = user_glosses_map(db, user)
    pref = user_script(user)
    for word in result.get("words", []):
        canonical_text = word.get("text", "")
        if states:
            state = states.get(canonical_text)
            if state is not None:
                word["user_state"] = state
        if glosses_map:
            user_glosses = glosses_map.get(canonical_text)
            if user_glosses:
                word["user_glosses"] = user_glosses
        if pref == "trad" and canonical_text:
            word["text"] = to_user_script(canonical_text, user)

    # Sentence text on the grammar payload also needs converting so the
    # SPA's sentence-translation chip shows the user's script.
    if pref == "trad":
        grammar = result.get("grammar", {})
        for sentence in grammar.get("sentences", []) if isinstance(grammar, dict) else []:
            if "text" in sentence:
                sentence["text"] = to_user_script(sentence["text"], user)

    return result
