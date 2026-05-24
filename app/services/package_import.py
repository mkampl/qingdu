"""
Pre-analyzed Qingdu package -> canonical analyze-response transformer.

The point of a package is to skip jieba + DeepL/Google translation
entirely: the LLM upstream already did the contextual disambiguation
(crucial for Daoist, Buddhist, Classical, legal corpora). The server's
job is just to layer on the corpus-level metadata it has dictionaries
for — HSK level, radicals, grammar patterns — without overriding what
the package author chose.
"""

from __future__ import annotations

from app.core.constants import TRANSLATION_SOURCE_HSK  # noqa: F401  re-exported style
from app.schemas import PackageToken, QingduPackage, WordInfo
from app.services import grammar
from app.services.levels import estimate_text_level
from app.state import hsk_vocab


class PackageImportError(Exception):
    """Raised when a package fails validation."""


def validate(package: QingduPackage, strict: bool = True) -> None:
    """
    Quick structural checks beyond what Pydantic gives us.

    - Every non-punct token must have a non-empty pinyin AND meaning.
    - In strict mode (the default), concatenating the tokens must reproduce
      the package's `text` field. Catches missed characters, normalised
      whitespace, etc.
    """
    if not package.text.strip():
        raise PackageImportError("Package `text` is empty.")
    if not package.tokens:
        raise PackageImportError("Package `tokens` is empty.")

    for i, tok in enumerate(package.tokens):
        if tok.is_punct:
            continue
        if not (tok.pinyin and tok.pinyin.strip()):
            raise PackageImportError(
                f"Token {i} ({tok.text!r}) is missing `pinyin`. "
                f"Non-punctuation tokens must include pinyin."
            )
        if not (tok.meaning and tok.meaning.strip()):
            raise PackageImportError(f"Token {i} ({tok.text!r}) is missing `meaning`.")

    if strict:
        joined = "".join(tok.text for tok in package.tokens)
        if joined != package.text:
            # Surface a brief diff hint to help the LLM author debug.
            mismatch_at = _first_diff(joined, package.text)
            raise PackageImportError(
                f"Token concatenation doesn't match `text` (first diff at "
                f"char {mismatch_at}). Use ?strict=false to bypass."
            )


def _first_diff(a: str, b: str) -> int:
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return min(len(a), len(b))


def _hsk_level_buckets() -> tuple[dict, dict, int, int]:
    """Empty buckets for the dual HSK distribution stats."""
    return ({f"hsk{i}": 0 for i in range(1, 10)}, {f"hsk{i}": 0 for i in range(1, 7)}, 0, 0)


def _bump_level(stats: dict, total: int, level: str | None, prefix: str) -> int:
    if not level:
        return total
    raw = level.replace(prefix, "").replace("+", "")
    try:
        key = f"hsk{int(raw)}"
        if key in stats:
            stats[key] += 1
        return total + 1
    except ValueError:
        return total


def _build_word_info(tok: PackageToken, package_source: str | None) -> WordInfo:
    """Build a single WordInfo from a package token, layering HSK metadata."""
    if tok.is_punct:
        # Punctuation passes through as a non-clickable token. We mark it
        # is_hsk=False so the reader skips popover wiring, and use the same
        # translation_source ("linebreak"-style flag) the analyse pipeline
        # uses for non-word tokens.
        return WordInfo(
            text=tok.text,
            is_hsk=False,
            hsk_level="",
            pinyin="",
            meaning="",
            meanings=[],
            frequency=0,
            translation_source="package",
            package_source=package_source,
        )

    vocab = hsk_vocab.get(tok.text, {}) or {}
    return WordInfo(
        text=tok.text,
        is_hsk=True,  # always renderable as a clickable word with a wash
        hsk_level=vocab.get("level", ""),
        level_new=vocab.get("level_new"),
        level_old=vocab.get("level_old"),
        pinyin=tok.pinyin or vocab.get("pinyin", ""),
        meaning=tok.meaning or vocab.get("meaning", ""),
        meanings=tok.meanings or ([tok.meaning] if tok.meaning else vocab.get("meanings", [])),
        frequency=vocab.get("frequency", 0),
        translation_source="package",
        package_source=package_source,
        notes=tok.notes,
        radical=vocab.get("radical", ""),
        radical_pinyin=vocab.get("radical_pinyin", ""),
    )


def transform(package: QingduPackage) -> dict:
    """
    Convert a validated package into a canonical analyze-response dict —
    same shape as `analyze_chinese_text` produces. The SPA renders the
    result through the existing ReadingText component unchanged.
    """
    hsk_stats_new, hsk_stats_old, total_new, total_old = _hsk_level_buckets()
    words: list[dict] = []

    for tok in package.tokens:
        wi = _build_word_info(tok, package.source)
        # Roll HSK stats — only for non-punct tokens that the dictionary
        # recognises, so the headline difficulty stays honest about the
        # corpus (the package author's translation choices are independent).
        if not tok.is_punct:
            total_new = _bump_level(hsk_stats_new, total_new, wi.level_new, "new-")
            total_old = _bump_level(hsk_stats_old, total_old, wi.level_old, "old-")
        words.append(wi.dict())

    estimated_new = estimate_text_level(hsk_stats_new, total_new)
    estimated_old = estimate_text_level(hsk_stats_old, total_old)

    # Grammar pattern detector — runs on the joined text, language-version
    # agnostic. Classical patterns won't match modern-Chinese rules well,
    # but that's fine: the detector just no-ops on missing patterns.
    grammar_sentences = _group_grammar_sentences(package.tokens)
    matches, metas = grammar.detect_patterns(grammar_sentences)
    grammar_payload = {
        "matches": [
            {
                "pattern_id": m.pattern_id,
                "sentence_idx": m.sentence_idx,
                "start_word_idx": m.start_word_idx,
                "end_word_idx": m.end_word_idx,
                "span_text": m.span_text,
            }
            for m in matches
        ],
        "patterns": metas,
    }

    return {
        "words": words,
        "grammar": grammar_payload,
        "statistics": {
            "total_characters": len(package.text),
            "total_words": len(package.tokens),
            "hsk_words_new": total_new,
            "hsk_distribution_new": hsk_stats_new,
            "estimated_level_new": estimated_new,
            "hsk_words_old": total_old,
            "hsk_distribution_old": hsk_stats_old,
            "estimated_level_old": estimated_old,
            # Legacy aliases.
            "hsk_words": total_new,
            "hsk_distribution": hsk_stats_new,
            "estimated_level": estimated_new,
        },
    }


_SENTENCE_END_CHARS = "。！？!?…"


def _group_grammar_sentences(
    tokens: list[PackageToken],
) -> list[tuple[int, grammar.Sentence]]:
    """Mirrors `_group_sentences` from segmentation — build per-sentence
    chunks with absolute token offsets for the grammar detector."""
    out: list[tuple[int, grammar.Sentence]] = []
    cur_words: list[str] = []
    cur_text: list[str] = []
    cur_start = 0
    for i, tok in enumerate(tokens):
        cur_words.append(tok.text)
        cur_text.append(tok.text)
        if any(p in tok.text for p in _SENTENCE_END_CHARS):
            out.append((cur_start, grammar.Sentence(words=cur_words, text="".join(cur_text))))
            cur_words = []
            cur_text = []
            cur_start = i + 1
    if cur_words:
        out.append((cur_start, grammar.Sentence(words=cur_words, text="".join(cur_text))))
    return out


__all__ = ["PackageImportError", "transform", "validate"]
