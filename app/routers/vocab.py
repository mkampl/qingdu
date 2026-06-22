from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import User, UserWord, get_db
from app.state import hsk_lists_original, hsk_vocab

router = APIRouter(tags=["Vocabulary"])


@router.get("/api/vocabulary-stats")
async def vocabulary_stats():
    """Return loaded vocabulary size and the per-level word count breakdown."""
    if not hsk_vocab:
        return {"loaded": False, "count": 0}

    level_counts: dict = {}
    for word_data in hsk_vocab.values():
        level = word_data["level"]
        level_counts[level] = level_counts.get(level, 0) + 1

    return {
        "loaded": True,
        "count": len(hsk_vocab),
        "by_level": level_counts,
    }


@router.get("/api/get-hsk-vocabulary")
async def get_hsk_vocabulary():
    """Return the full HSK vocabulary for text analysis (with supplementation)."""
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")
    return hsk_vocab


@router.get("/api/get-hsk-lists-original")
async def get_hsk_lists_original():
    """Return the original HSK vocabulary for list generation (no supplementation)."""
    if not hsk_lists_original:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")
    return hsk_lists_original


@router.get("/api/vocab/hsk")
async def browse_hsk(
    level: str | None = Query(None, description="HSK level filter like 'new-3' or 'old-2'"),
    q: str | None = Query(None, description="Substring match on hanzi/pinyin/meaning"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated HSK catalog — the Browse tab's data source.

    Joins the caller's per-word state (UserWord.state) when authenticated
    so the UI can render 'Add to learning' vs 'Already learning' without
    a second round-trip per row.
    """
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")

    needle = q.strip().lower() if q else None

    # Single-pass filter so we don't allocate twice. The dict is ~10k entries
    # so we accept the O(n) scan per request — much simpler than maintaining
    # a separate index, and small enough to be fast.
    matched: list[tuple[str, dict]] = []
    for hanzi, data in hsk_vocab.items():
        if level is not None:
            ln = data.get("level_new")
            lo = data.get("level_old")
            if ln != level and lo != level:
                continue
        if needle is not None:
            pinyin = (data.get("pinyin") or "").lower()
            meaning = (data.get("meaning") or "").lower()
            if needle not in hanzi.lower() and needle not in pinyin and needle not in meaning:
                continue
        matched.append((hanzi, data))

    # Stable-ish sort: by level_new then hanzi so 'HSK 1' lands before 'HSK 2'
    # and within a level the order is deterministic across requests.
    def _sort_key(item: tuple[str, dict]) -> tuple:
        _hanzi, d = item
        ln = d.get("level_new") or d.get("level_old") or "zzz"
        # Extract numeric part to sort 'new-2' before 'new-10' naturally.
        try:
            n = int(ln.split("-", 1)[1])
        except (ValueError, IndexError):
            n = 99
        return (n, _hanzi)

    matched.sort(key=_sort_key)
    total = len(matched)
    page = matched[offset : offset + limit]

    # Join user state if authenticated.
    states: dict[str, str] = {}
    if user is not None and page:
        words = [h for h, _ in page]
        rows = (
            db.query(UserWord.word, UserWord.state)
            .filter(UserWord.user_id == user.id, UserWord.word.in_(words))
            .all()
        )
        states = dict(rows)

    items = [
        {
            "hanzi": hanzi,
            "pinyin": data.get("pinyin"),
            "meaning": data.get("meaning"),
            "meanings": data.get("meanings") or [],
            "level_new": data.get("level_new"),
            "level_old": data.get("level_old"),
            "frequency": data.get("frequency"),
            "user_state": states.get(hanzi),  # None = 'new'
        }
        for hanzi, data in page
    ]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/api/debug/vocab-sample")
async def debug_vocab_sample():
    """Sample first 20 entries — used to verify level_old population."""
    if not hsk_vocab:
        return {"error": "Vocabulary not loaded"}

    sample: dict = {}
    count_with_both = 0
    count_new_only = 0
    count_old_only = 0

    for i, (word, data) in enumerate(hsk_vocab.items()):
        if i < 20:
            sample[word] = {
                "level": data.get("level"),
                "level_new": data.get("level_new"),
                "level_old": data.get("level_old"),
                "pinyin": data.get("pinyin"),
                "meaning": data.get("meaning"),
            }
        has_new = data.get("level_new") is not None
        has_old = data.get("level_old") is not None
        if has_new and has_old:
            count_with_both += 1
        elif has_new:
            count_new_only += 1
        elif has_old:
            count_old_only += 1

    return {
        "sample": sample,
        "statistics": {
            "total_words": len(hsk_vocab),
            "with_both_levels": count_with_both,
            "new_hsk_only": count_new_only,
            "old_hsk_only": count_old_only,
        },
    }


@router.get("/api/debug/vocab-lookup/{word}")
async def debug_vocab_lookup(word: str):
    """Debug endpoint — look up one word, falling back to per-character data."""
    if not hsk_vocab:
        return {"error": "Vocabulary not loaded"}

    if word in hsk_vocab:
        return {"found": True, "word": word, "data": hsk_vocab[word]}

    char_data = {char: hsk_vocab[char] for char in word if char in hsk_vocab}
    return {
        "found": False,
        "word": word,
        "message": "Word not in vocabulary",
        "characters": char_data if char_data else "No character data found",
    }
