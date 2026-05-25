import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.core.constants import ANALYZE_RATE_LIMIT
from app.core.rate_limit import limiter
from app.database import User, UserWord, VocabularyList, get_db
from app.schemas import TextAnalysisRequest
from app.services.script import to_canonical, to_user_script, user_script
from app.services.segmentation import analyze_chinese_text
from app.state import hsk_vocab

router = APIRouter(tags=["Analysis"])


def _user_state_map(db: Session, user: User | None) -> dict[str, str]:
    """Fetch the user's full word-state map. Cheap: a single indexed query."""
    if user is None:
        return {}
    rows = db.query(UserWord.word, UserWord.state).filter(UserWord.user_id == user.id).all()
    return dict(rows)


def _build_glossary(
    db: Session,
    user: User | None,
    list_ids: list[int] | None,
) -> dict[str, dict]:
    """
    Resolve the picker selection to a {word: {pinyin, meaning, list_name}} map.

    Semantics:
      - user is None              -> empty map (anonymous can't use a glossary)
      - list_ids is None          -> use every list the user has flagged
      - list_ids == []            -> explicitly use no glossary
      - list_ids == [3, 5]        -> use only those lists (ignoring others)

    Multi-list conflicts: later-created lists win (ORDER BY created_at DESC,
    so the most recently-curated glossary takes priority).
    """
    if user is None or list_ids == []:
        return {}

    q = db.query(VocabularyList).filter(
        VocabularyList.user_id == user.id,
        VocabularyList.apply_as_glossary.is_(True),
    )
    if list_ids:
        q = q.filter(VocabularyList.id.in_(list_ids))
    lists = q.order_by(VocabularyList.created_at.asc()).all()

    out: dict[str, dict] = {}
    for vl in lists:
        try:
            sections = json.loads(vl.sections) if vl.sections else []
        except (ValueError, TypeError):
            continue
        for section in sections:
            for word in section.get("words", []) or []:
                hanzi = (word.get("hanzi") or "").strip()
                if not hanzi:
                    continue
                # Iteration order is oldest-list first, so newer lists
                # naturally overwrite. Inside one list, last word wins.
                out[hanzi] = {
                    "pinyin": (word.get("pinyin") or "").strip(),
                    "meaning": (word.get("meaning") or "").strip(),
                    "meanings": word.get("meanings") or [],
                    "list_name": vl.name,
                    "list_id": vl.id,
                }
    return out


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
async def analyze_text(
    request: Request,
    data: TextAnalysisRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
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

    glossary = _build_glossary(db, user, data.glossary_list_ids)
    result = await analyze_chinese_text(text_simp, glossary=glossary)

    # Enrich words with per-user state when the request is authenticated.
    # Anonymous callers get the response unchanged. Lookup happens against
    # the canonical (simp) text before we convert anything to the user's
    # display script.
    states = _user_state_map(db, user)
    pref = user_script(user)
    for word in result.get("words", []):
        canonical_text = word.get("text", "")
        if states:
            state = states.get(canonical_text)
            if state is not None:
                word["user_state"] = state
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
