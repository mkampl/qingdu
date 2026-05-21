from fastapi import APIRouter, HTTPException

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
