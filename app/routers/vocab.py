from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import User, UserWord, get_db
from app.services.readings import readings_payload
from app.state import hsk_vocab

router = APIRouter(tags=["Vocabulary"])

# Word states the Browse tab can filter on; "new" means no UserWord row.
BROWSE_STATES = ("new", "learning", "known", "ignored")


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


@router.get("/api/vocab/hsk")
async def browse_hsk(
    level: str | None = Query(None, description="HSK level filter like 'new-3' or 'old-2'"),
    q: str | None = Query(None, description="Substring match on hanzi/pinyin/meaning"),
    state: str | None = Query(
        None,
        description="Comma list of the caller's word states: new, learning, known, ignored",
    ),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated HSK catalog — the Browse tab's data source.

    Joins the caller's per-word state (UserWord.state) when authenticated
    so the UI can render 'Add to learning' vs 'Already learning' without
    a second round-trip per row. `state` filters on that state ('new' = no
    row) before paging, and `state_counts` reports how the level/search
    result splits across the states, so the UI can show "HSK 3 · 120 known".
    """
    if not hsk_vocab:
        raise HTTPException(status_code=503, detail="Vocabulary not loaded yet")

    wanted_states: set[str] | None = None
    if state:
        wanted_states = {s.strip() for s in state.split(",") if s.strip()}
        unknown = wanted_states - set(BROWSE_STATES)
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"state must be among {', '.join(BROWSE_STATES)}",
            )

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

    # The caller's states for the whole catalog: a few hundred to a few
    # thousand rows, cheaper than an IN list over the matched words.
    states: dict[str, str] = {}
    if user is not None:
        states = dict(
            db.query(UserWord.word, UserWord.state).filter(UserWord.user_id == user.id).all()
        )

    state_counts = dict.fromkeys(BROWSE_STATES, 0)
    for hanzi, _data in matched:
        st = states.get(hanzi, "new")
        if st in state_counts:
            state_counts[st] += 1
    if wanted_states is not None:
        matched = [m for m in matched if states.get(m[0], "new") in wanted_states]

    matched.sort(key=_sort_key)
    total = len(matched)
    page = matched[offset : offset + limit]

    items = [
        {
            "hanzi": hanzi,
            "pinyin": data.get("pinyin"),
            "meaning": data.get("meaning"),
            "meanings": data.get("meanings") or [],
            "meaning_tags": data.get("meaning_tags") or [],
            "readings": readings_payload(data),
            "level_new": data.get("level_new"),
            "level_old": data.get("level_old"),
            "frequency": data.get("frequency"),
            "user_state": states.get(hanzi),  # None = 'new'
        }
        for hanzi, data in page
    ]
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "state_counts": state_counts,
    }


@router.get("/api/debug/vocab-lookup/{word}")
async def debug_vocab_lookup(word: str, _admin: User = Depends(require_admin)):
    """Admin debug endpoint — the raw dictionary entry for one word, falling
    back to per-character data."""
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
