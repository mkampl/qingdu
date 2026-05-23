"""
Chinese text segmentation + HSK enrichment.

The route handler in `app.routers.analyze` is a thin wrapper around
`analyze_chinese_text` — keep all the segmentation logic here.
"""

import asyncio
import logging
import time

import jieba

from app.core.constants import TRANSLATION_SOURCE_HSK
from app.schemas import WordInfo
from app.services import grammar
from app.services.levels import estimate_text_level
from app.services.word_lookup import create_compound_from_hsk, lookup_unknown_word
from app.state import hsk_vocab

_SENTENCE_END_CHARS = "。！？!?…"

logger = logging.getLogger(__name__)

# How many unknown-word lookups we'll fire in parallel. Each lookup hits the
# DeepL/Google/MyMemory chain via a single httpx client, so the real
# concurrency on each provider is at most this. Pick conservatively — too
# high and we'll trip DeepL/MyMemory rate limits, too low and long imports
# remain slow. 8 is empirically fine for a single learner.
_LOOKUP_CONCURRENCY = 8


def get_word_info(word: str) -> dict | None:
    """Look up a word in the HSK vocab. Returns None if not found."""
    return hsk_vocab.get(word)


def _increment_level(stats: dict, total: int, level: str | None, prefix: str) -> int:
    """
    Increment the stats bucket for `level` (e.g. "new-3" -> "hsk3").
    Returns the new total (caller does `total = _increment_level(...)`).
    """
    if not level:
        return total
    level_num = level.replace(prefix, "").replace("+", "")
    try:
        key = f"hsk{int(level_num)}"
        if key in stats:
            stats[key] += 1
        return total + 1
    except ValueError:
        return total


def _needs_lookup(segment: str) -> str | None:
    """
    Return the *kind* of lookup this segment needs, or None if it doesn't.

    'compound' -> create_compound_from_hsk (every char is in HSK)
    'unknown'  -> lookup_unknown_word
    None       -> in HSK directly, single char, or whitespace/linebreak
    """
    if not segment or segment == "\n":
        return None
    if get_word_info(segment) is not None:
        return None
    if len(segment) <= 1:
        return None
    if all(char in hsk_vocab for char in segment):
        return "compound"
    return "unknown"


async def _resolve_unknowns(
    segments: list[str],
) -> dict[str, dict | None]:
    """
    Collect unique segments that need online lookup, fire all the calls
    concurrently (bounded by _LOOKUP_CONCURRENCY), and return a map of
    segment -> resolved info dict. Sequential lookups dominated total time
    for imported articles; this is where the speedup comes from.
    """
    unique = {}  # ordered: insertion order = first occurrence in text
    for seg in segments:
        kind = _needs_lookup(seg)
        if kind and seg not in unique:
            unique[seg] = kind

    if not unique:
        return {}

    started = time.monotonic()
    sem = asyncio.Semaphore(_LOOKUP_CONCURRENCY)

    async def _resolve(seg: str, kind: str) -> tuple[str, dict | None]:
        async with sem:
            if kind == "compound":
                info = await create_compound_from_hsk(seg)
            else:
                info = await lookup_unknown_word(seg)
            return seg, info

    results = await asyncio.gather(
        *(_resolve(seg, kind) for seg, kind in unique.items()),
        return_exceptions=False,
    )
    elapsed = time.monotonic() - started
    logger.info(
        "Resolved %d unknown segments in %.2fs (concurrency=%d)",
        len(unique),
        elapsed,
        _LOOKUP_CONCURRENCY,
    )
    return dict(results)


def _group_sentences(segments: list[str]) -> list[tuple[int, grammar.Sentence]]:
    """
    Walk the segmented tokens (in 1:1 correspondence with the response's
    `words` array) and group them into sentences for grammar detection.
    Returns (absolute_word_offset, Sentence) tuples so the detector can
    emit globally-positioned spans.
    """
    out: list[tuple[int, grammar.Sentence]] = []
    cur_words: list[str] = []
    cur_text: list[str] = []
    cur_start = 0
    for i, seg in enumerate(segments):
        if seg == "\n":
            if cur_words:
                out.append((cur_start, grammar.Sentence(words=cur_words, text="".join(cur_text))))
                cur_words = []
                cur_text = []
            cur_start = i + 1
            continue
        cur_words.append(seg)
        cur_text.append(seg)
        if any(p in seg for p in _SENTENCE_END_CHARS):
            out.append((cur_start, grammar.Sentence(words=cur_words, text="".join(cur_text))))
            cur_words = []
            cur_text = []
            cur_start = i + 1
    if cur_words:
        out.append((cur_start, grammar.Sentence(words=cur_words, text="".join(cur_text))))
    return out


async def analyze_chinese_text(text: str) -> dict:
    """
    Segment `text` with jieba, look each word up in the HSK vocab (falling back
    to compound-from-characters or an online lookup), and return per-word data
    plus aggregate statistics across both HSK systems.
    """
    text = text.strip()
    if not text:
        return {"words": [], "statistics": {}}

    # Split by line breaks first so we can preserve them in the output.
    lines = text.split("\n")
    segments: list = []
    for i, line in enumerate(lines):
        if line.strip():
            segments.extend(list(jieba.cut(line)))
        if i < len(lines) - 1:
            segments.append("\n")

    # Pass 1: kick off every online lookup concurrently. The result is a
    # dict keyed by segment text, so the per-segment loop below is pure
    # local work — no awaits, no head-of-line blocking.
    resolved = await _resolve_unknowns(segments)

    words: list = []
    hsk_stats_new = {f"hsk{i}": 0 for i in range(1, 10)}
    hsk_stats_old = {f"hsk{i}": 0 for i in range(1, 7)}  # Old HSK has 6 levels
    total_hsk_words_new = 0
    total_hsk_words_old = 0

    for segment in segments:
        if segment == "\n":
            words.append(
                WordInfo(
                    text="\n",
                    is_hsk=False,
                    hsk_level="",
                    pinyin="",
                    meaning="",
                    meanings=[],
                    frequency=0,
                    translation_source="linebreak",
                ).dict()
            )
            continue

        word_info = WordInfo(text=segment)
        vocab_entry = get_word_info(segment)

        if vocab_entry:
            word_info.hsk_level = vocab_entry["level"]
            word_info.level_new = vocab_entry.get("level_new")
            word_info.level_old = vocab_entry.get("level_old")
            word_info.pinyin = vocab_entry["pinyin"]
            word_info.meaning = vocab_entry["meaning"]
            word_info.meanings = vocab_entry["meanings"]
            word_info.frequency = vocab_entry["frequency"]
            word_info.is_hsk = True
            word_info.translation_source = TRANSLATION_SOURCE_HSK
            word_info.radical = vocab_entry.get("radical", "")
            word_info.radical_pinyin = vocab_entry.get("radical_pinyin", "")
            total_hsk_words_new = _increment_level(
                hsk_stats_new, total_hsk_words_new, vocab_entry.get("level_new"), "new-"
            )
            total_hsk_words_old = _increment_level(
                hsk_stats_old, total_hsk_words_old, vocab_entry.get("level_old"), "old-"
            )
        elif len(segment) > 1:
            info = resolved.get(segment)
            if info:
                # Compound (every char in HSK) brings both new and old levels;
                # generic unknowns don't, so we branch on the presence of
                # 'level_new'/'level_old' fields rather than re-deriving the
                # 'compound' vs 'unknown' decision here.
                is_compound = info.get("level_new") is not None or info.get("level_old") is not None
                if is_compound:
                    word_info.hsk_level = info["level"]
                    word_info.level_new = info.get("level_new")
                    word_info.level_old = info.get("level_old")
                    word_info.pinyin = info["pinyin"]
                    word_info.meaning = info["meaning"]
                    word_info.meanings = info["meanings"]
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    word_info.translation_source = info.get("translation_source")
                    word_info.radical = info.get("radical", "")
                    word_info.radical_pinyin = info.get("radical_pinyin", "")
                    total_hsk_words_new = _increment_level(
                        hsk_stats_new,
                        total_hsk_words_new,
                        info.get("level_new"),
                        "new-",
                    )
                    total_hsk_words_old = _increment_level(
                        hsk_stats_old,
                        total_hsk_words_old,
                        info.get("level_old"),
                        "old-",
                    )
                else:
                    word_info.hsk_level = "unknown"
                    word_info.level_new = None
                    word_info.level_old = None
                    word_info.pinyin = info["pinyin"]
                    word_info.meaning = info["meaning"]
                    word_info.meanings = info["meanings"]
                    word_info.frequency = 0
                    word_info.is_hsk = True
                    word_info.translation_source = info.get("translation_source")

        words.append(word_info.dict())

    estimated_level_new = estimate_text_level(hsk_stats_new, total_hsk_words_new)
    estimated_level_old = estimate_text_level(hsk_stats_old, total_hsk_words_old)

    # Grammar patterns: rule-based, cheap, runs after segmentation. Spans
    # carry absolute word indices so the SPA can map them straight onto
    # its already-rendered word elements.
    pattern_matches, pattern_metas = grammar.detect_patterns(_group_sentences(segments))
    grammar_payload = {
        "matches": [
            {
                "pattern_id": m.pattern_id,
                "sentence_idx": m.sentence_idx,
                "start_word_idx": m.start_word_idx,
                "end_word_idx": m.end_word_idx,
                "span_text": m.span_text,
            }
            for m in pattern_matches
        ],
        "patterns": pattern_metas,
    }

    return {
        "words": words,
        "grammar": grammar_payload,
        "statistics": {
            "total_characters": len(text),
            "total_words": len(segments),
            "hsk_words_new": total_hsk_words_new,
            "hsk_distribution_new": hsk_stats_new,
            "estimated_level_new": estimated_level_new,
            "hsk_words_old": total_hsk_words_old,
            "hsk_distribution_old": hsk_stats_old,
            "estimated_level_old": estimated_level_old,
            # Legacy fields (for backwards compatibility — use new HSK).
            "hsk_words": total_hsk_words_new,
            "hsk_distribution": hsk_stats_new,
            "estimated_level": estimated_level_new,
        },
    }
