"""
Chinese text segmentation + HSK enrichment.

The route handler in `app.routers.analyze` is a thin wrapper around
`analyze_chinese_text` — keep all the segmentation logic here.
"""

import logging

import jieba

from app.core.constants import HSK_WORD_BASE_FREQ, TRANSLATION_SOURCE_HSK
from app.schemas import WordInfo
from app.services import grammar
from app.services.levels import estimate_text_level
from app.services.lexicon import (
    dictionaries_loaded,
    in_dictionary,
    is_cjk_word,
    split_into_known,
)
from app.services.readings import readings_payload
from app.services.word_lookup import describe_non_word, resolve_from_cedict
from app.state import hsk_vocab

_SENTENCE_END_CHARS = "。！？!?…"

logger = logging.getLogger(__name__)


def prime_jieba() -> int:
    """Initialise jieba and add every multi-character HSK word to its
    dictionary with a high frequency, so HSK words win over jieba's own
    phrase entries. Called once at startup, after the HSK list loaded.
    Returns the number of words added."""
    jieba.initialize()
    added = 0
    for word, data in hsk_vocab.items():
        if len(word) > 1:
            jieba.add_word(word, freq=max(data.get("frequency", 0) * 100, HSK_WORD_BASE_FREQ))
            added += 1
    return added


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


def _refine_token(token: str, glossary: dict) -> list[str]:
    """Keep a token that is a word (HSK, CC-CEDICT, the user's glossary);
    split anything else into the dictionary words it is made of.

    jieba's dictionary is full of phrases (很多, 三个, 洗衣服, 第一个) that
    are not words for a learner; they used to come out as one token with
    a glued "very + many" gloss. Non-Chinese tokens and single characters
    pass through unchanged."""
    if len(token) <= 1 or token in glossary or not is_cjk_word(token):
        return [token]
    if in_dictionary(token) or not dictionaries_loaded():
        return [token]
    return split_into_known(token, glossary)


# Longest glossary term (in tokens) that _join_glossary_terms puts back together.
_GLOSSARY_JOIN_MAX_TOKENS = 8


def _join_glossary_terms(tokens: list[str], glossary: dict) -> list[str]:
    """Join runs of tokens that spell a term of the user's glossary.

    jieba does not know a list's own terms (抱元守一, 三功九秘) and cuts
    them up; a glossary term is one word for the user, so the reader
    shows it whole with the list's meaning. The longest term starting at
    a token wins. A term that would cut through a token is left alone."""
    if not glossary:
        return tokens
    longest = max((len(k) for k in glossary), default=0)
    out: list[str] = []
    i = 0
    while i < len(tokens):
        best = None
        joined = ""
        for j in range(i, min(len(tokens), i + _GLOSSARY_JOIN_MAX_TOKENS)):
            joined += tokens[j]
            if len(joined) > longest:
                break
            if j > i and joined in glossary:
                best = j
        if best is None:
            out.append(tokens[i])
            i += 1
        else:
            out.append("".join(tokens[i : best + 1]))
            i = best + 1
    return out


def segment_text(text: str, glossary: dict | None = None) -> list[str]:
    """Tokens of `text` in reading order, with "\n" for every line break.

    Every jieba token that is not a word is split by `_refine_token`.
    jieba's HMM stays on: it only joins runs of single characters, and
    what it invents is either a dictionary word jieba's own word list
    lacks (公钥, 食材, 点赞, 内卷: kept) or a non-word (我来, 太热, 我点:
    split again). With the HMM off those dictionary words came out as
    single characters, and the non-words come out the same either way.
    Terms of the user's glossary that jieba cut up are joined again."""
    glossary = glossary or {}
    lines = text.split("\n")
    segments: list[str] = []
    for i, line in enumerate(lines):
        if line.strip():
            tokens: list[str] = []
            for token in jieba.cut(line):
                tokens.extend(_refine_token(token, glossary))
            segments.extend(_join_glossary_terms(tokens, glossary))
        if i < len(lines) - 1:
            segments.append("\n")
    return segments


def _resolve_non_hsk(segments: list[str], glossary: dict) -> dict[str, dict | None]:
    """Info for every segment that is not an HSK headword or a glossary
    entry: the CC-CEDICT entry when there is one, otherwise (for several
    characters) a reading plus the token's dictionary parts. All local, no
    network: isolated tokens are never sent to a translation service."""
    resolved: dict[str, dict | None] = {}
    for seg in segments:
        if seg in resolved or not seg or seg == "\n":
            continue
        if seg in glossary or get_word_info(seg) is not None:
            continue
        if len(seg) == 1:
            resolved[seg] = resolve_from_cedict(seg) if is_cjk_word(seg) else None
            continue
        resolved[seg] = resolve_from_cedict(seg) or describe_non_word(seg, glossary)
    return resolved


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


async def analyze_chinese_text(
    text: str,
    glossary: dict[str, dict] | None = None,
) -> dict:
    """
    Segment `text` (see `segment_text`), look each word up in the HSK vocab
    (falling back to CC-CEDICT, or to the token's dictionary parts), and
    return per-word data plus aggregate statistics across both HSK systems.

    `glossary`, if provided, is a {word: {pinyin, meaning, list_name}} map
    built by the caller from the user's glossary-flagged vocabulary lists.
    On glossary hit, the word's pinyin + meaning come from the user instead
    of HSK / online lookup; HSK level (when the word is also in HSK) is
    still attached so the corpus difficulty signal stays honest.
    """
    text = text.strip()
    if not text:
        return {"words": [], "statistics": {}}
    glossary = glossary or {}

    segments = segment_text(text, glossary)
    resolved = _resolve_non_hsk(segments, glossary)

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

        # Glossary takes priority over HSK lookup. HSK metadata (level,
        # radical) is still attached so the difficulty signal + radical
        # popover work — only the meaning/pinyin/source get overridden.
        glossary_hit = glossary.get(segment)
        if glossary_hit:
            vocab_entry = get_word_info(segment) or {}
            word_info.hsk_level = vocab_entry.get("level", "")
            word_info.level_new = vocab_entry.get("level_new")
            word_info.level_old = vocab_entry.get("level_old")
            word_info.pinyin = glossary_hit.get("pinyin", "") or vocab_entry.get("pinyin", "")
            word_info.meaning = glossary_hit.get("meaning", "")
            word_info.meanings = glossary_hit.get("meanings") or [glossary_hit.get("meaning", "")]
            word_info.frequency = vocab_entry.get("frequency", 0)
            word_info.is_hsk = True  # ensures the reader treats it as a clickable, colored word
            word_info.translation_source = "glossary"
            word_info.glossary_source = glossary_hit.get("list_name")
            word_info.radical = vocab_entry.get("radical", "")
            word_info.radical_pinyin = vocab_entry.get("radical_pinyin", "")
            # Don't roll glossary hits into HSK stats — keeps the chart honest
            # about what's in the corpus vs what's overridden.
            words.append(word_info.dict())
            continue

        vocab_entry = get_word_info(segment)

        if vocab_entry:
            word_info.hsk_level = vocab_entry["level"]
            word_info.level_new = vocab_entry.get("level_new")
            word_info.level_old = vocab_entry.get("level_old")
            word_info.pinyin = vocab_entry["pinyin"]
            word_info.meaning = vocab_entry["meaning"]
            word_info.meanings = vocab_entry["meanings"]
            word_info.meaning_tags = vocab_entry.get("meaning_tags") or None
            word_info.readings = readings_payload(vocab_entry)
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
        else:
            info = resolved.get(segment)
            if info:
                word_info.parts = info.get("parts") or None
                # Words made only of HSK characters bring both new and old
                # levels; others don't, so we branch on the presence of
                # 'level_new'/'level_old' rather than re-deriving it here.
                is_compound = info.get("level_new") is not None or info.get("level_old") is not None
                if is_compound:
                    word_info.hsk_level = info["level"]
                    word_info.level_new = info.get("level_new")
                    word_info.level_old = info.get("level_old")
                    word_info.pinyin = info["pinyin"]
                    word_info.meaning = info["meaning"]
                    word_info.meanings = info["meanings"]
                    word_info.meaning_tags = info.get("meaning_tags") or None
                    word_info.readings = info.get("readings") or None
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
                    word_info.meaning_tags = info.get("meaning_tags") or None
                    word_info.readings = info.get("readings") or None
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
