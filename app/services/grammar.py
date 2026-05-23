"""
Sentence-pattern detection for the reader.

Phase D ships ~10 high-value HSK 1–3 grammar patterns as inline annotations.
The detector runs after jieba segmentation and emits per-pattern matches
with their token-range positions so the SPA can underline + popover them.

Why regex-on-text, not token equality:
    jieba happily fuses "越来越" into a single token and "因为" into a
    standalone one. Matching by token text would either miss the colloquial
    "越来越" form of 越…越 or require a lookup table for every fused variant.
    Matching on the raw sentence text and projecting the char span back to
    token indices is more robust and ages better as the corpus changes.

Adding patterns:
    Append a `PatternDef` to PATTERNS with a unique `id`, a regex, and a
    short explanation. The regex runs against the raw sentence text. Spans
    are token-aligned automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Sentence:
    """Minimal sentence shape the detector needs. `words` are jieba tokens
    in reading order; `text` is the joined original text."""

    words: list[str]
    text: str


@dataclass
class PatternMatch:
    pattern_id: str
    sentence_idx: int
    start_word_idx: int  # absolute index into the analyse response's `words`
    end_word_idx: int  # absolute index into `words` (inclusive)
    span_text: str


@dataclass
class PatternDef:
    id: str
    title: str
    pinyin: str
    hsk_level: int
    explanation: str
    example: str
    example_translation: str
    # Regex applied to Sentence.text. The pattern's full match span (group 0)
    # is what gets highlighted; named subgroups are ignored.
    regex: re.Pattern[str]


# Patterns ordered roughly by HSK level so the "first to match" semantics
# in the SPA pick the more elementary pattern when two overlap.

PATTERNS: list[PatternDef] = [
    PatternDef(
        id="shi-de",
        title="是…的",
        pinyin="shì … de",
        hsk_level=2,
        explanation=(
            "Used to emphasise when, where, how, or by whom a past action happened. "
            "The 是 introduces the emphasised element; 的 closes the structure."
        ),
        example="我是昨天来的。",
        example_translation='I came yesterday. (emphasis on "yesterday")',
        # Need at least one character between 是 and 的; bare 是的 ("yes") is
        # not the emphasis construction.
        regex=re.compile(r"是[^。！？!?…]{1,30}?的"),
    ),
    PatternDef(
        id="ba",
        title="把 disposal",
        pinyin="bǎ",
        hsk_level=3,
        explanation=(
            "Moves the object in front of the verb to emphasise what was done to it. "
            'Often translated as "take X and …" — "I took the book and read it."'
        ),
        example="我把书读完了。",
        example_translation="I finished reading the book.",
        # 把 + at least one follow-up character. False positives on idioms
        # like 一把 are tolerable — better to highlight than to miss.
        regex=re.compile(r"把[一-鿿]{1,8}"),
    ),
    PatternDef(
        id="bei",
        title="被 passive",
        pinyin="bèi",
        hsk_level=3,
        explanation=(
            "Marks the passive voice: the subject is acted upon. 被 introduces the "
            "agent (optional) and is followed by the verb."
        ),
        example="苹果被吃了。",
        example_translation="The apple was eaten.",
        regex=re.compile(r"被[一-鿿]{1,8}"),
    ),
    PatternDef(
        id="yue-yue",
        title="越…越…",
        pinyin="yuè … yuè …",
        hsk_level=3,
        explanation=(
            '"The more X, the more Y." Pairs two qualities or actions that increase '
            "together. The collocation 越来越 (increasingly) is the same structure."
        ),
        example="天气越来越冷。",
        example_translation="The weather is getting colder and colder.",
        # Two 越 with up to a handful of characters between. Sentence-end
        # punctuation breaks the run.
        regex=re.compile(r"越[一-鿿]{0,10}?越"),
    ),
    PatternDef(
        id="yibian-yibian",
        title="一边…一边…",
        pinyin="yìbiān … yìbiān …",
        hsk_level=3,
        explanation=(
            'Two simultaneous actions. "While doing X, also doing Y." Each verb '
            "phrase is preceded by 一边."
        ),
        example="他一边吃饭一边看电视。",
        example_translation="He eats while watching TV.",
        regex=re.compile(r"一边[一-鿿]{1,15}?一边[一-鿿]{1,15}"),
    ),
    PatternDef(
        id="yinwei-suoyi",
        title="因为…所以…",
        pinyin="yīnwèi … suǒyǐ …",
        hsk_level=2,
        explanation=(
            '"Because X, therefore Y." Cause-and-effect pair. Either half can be '
            "dropped in colloquial speech, but here we only highlight the complete form."
        ),
        example="因为下雨,所以我没去。",
        example_translation="Because it rained, I didn't go.",
        regex=re.compile(r"(?:因为|由于)[一-鿿,，]{1,30}?所以[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="suiran-danshi",
        title="虽然…但是…",
        pinyin="suīrán … dànshì …",
        hsk_level=3,
        explanation=(
            '"Although X, but Y." 但是 can be replaced with 可是 or 不过 with no change in meaning.'
        ),
        example="虽然累,但是很开心。",
        example_translation="Although tired, I'm very happy.",
        regex=re.compile(r"虽然[一-鿿,，]{1,30}?(?:但是|可是|不过)[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="budan-erqie",
        title="不但…而且…",
        pinyin="búdàn … érqiě …",
        hsk_level=3,
        explanation=(
            '"Not only X, but also Y." 不但 can be replaced with 不仅; the second '
            "half often uses 还 / 也 instead of 而且."
        ),
        example="他不但聪明,而且很努力。",
        example_translation="He's not only smart, but also hardworking.",
        regex=re.compile(r"(?:不但|不仅)[一-鿿,，]{1,25}?(?:而且|并且)[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="ruguo-jiu",
        title="如果…就…",
        pinyin="rúguǒ … jiù …",
        hsk_level=2,
        explanation=(
            '"If X, then Y." The most common conditional. 如果 can be replaced with 要是 or 假如.'
        ),
        example="如果你有时间,就来。",
        example_translation="If you have time, come over.",
        regex=re.compile(r"(?:如果|要是|假如)[一-鿿,，]{1,30}?就[一-鿿]{1,10}"),
    ),
    PatternDef(
        id="le-aspect",
        title="了 — completed action",
        pinyin="le",
        hsk_level=1,
        explanation=(
            "Marks an action as completed (post-verbal 了) or a change of state "
            "(sentence-final 了). Worth re-reading whenever you spot it — the position "
            "shifts the meaning."
        ),
        example="我吃了饭。",
        example_translation="I have eaten.",
        # Highlight a verb + 了 cluster. We bound to 1 preceding CJK char to
        # keep the span tight; only the first occurrence per sentence fires.
        regex=re.compile(r"[一-鿿]了"),
    ),
]

_PATTERN_BY_ID = {p.id: p for p in PATTERNS}


def pattern_meta(pattern_id: str) -> dict:
    p = _PATTERN_BY_ID[pattern_id]
    return {
        "id": p.id,
        "title": p.title,
        "pinyin": p.pinyin,
        "hsk_level": p.hsk_level,
        "explanation": p.explanation,
        "example": p.example,
        "example_translation": p.example_translation,
    }


def _token_range_for_char_span(
    words: list[str], char_start: int, char_end: int
) -> tuple[int, int] | None:
    """
    Walk tokens until we find the smallest [first, last] index range whose
    combined character span covers [char_start, char_end). Returns None if
    the sentence text and the joined-tokens string don't align (shouldn't
    happen — the caller builds Sentence.text as "".join(words)).
    """
    pos = 0
    first = None
    last = None
    for i, w in enumerate(words):
        tok_start = pos
        tok_end = pos + len(w)
        # Token overlaps the requested char range?
        if tok_end > char_start and tok_start < char_end:
            if first is None:
                first = i
            last = i
        pos = tok_end
        if pos >= char_end and first is not None:
            break
    if first is None or last is None:
        return None
    return first, last


def detect_patterns(
    sentences: list[tuple[int, Sentence]],
) -> tuple[list[PatternMatch], list[dict]]:
    """
    Walk every sentence and collect pattern matches.

    `sentences` is a list of (sentence_start_word_idx, Sentence) — the
    caller knows the absolute word offset into `analysis_words` for each
    sentence so we can return globally-positioned spans.

    Returns (matches, unique_pattern_metas). `unique_pattern_metas` is the
    set of patterns that fired at least once, in the order they first
    appeared; the SPA uses it to render the sidebar panel.
    """
    matches: list[PatternMatch] = []
    seen_ids: set[str] = set()
    metas_in_order: list[dict] = []

    for sentence_idx, (offset, sentence) in enumerate(sentences):
        # le-aspect fires on basically every past-tense sentence; cap it at
        # one match per sentence so it remains a callout, not noise.
        le_seen_this_sentence = False
        for pattern in PATTERNS:
            for m in pattern.regex.finditer(sentence.text):
                if pattern.id == "le-aspect":
                    if le_seen_this_sentence:
                        continue
                    le_seen_this_sentence = True
                token_range = _token_range_for_char_span(sentence.words, m.start(), m.end())
                if token_range is None:
                    continue
                first, last = token_range
                matches.append(
                    PatternMatch(
                        pattern_id=pattern.id,
                        sentence_idx=sentence_idx,
                        start_word_idx=offset + first,
                        end_word_idx=offset + last,
                        span_text=m.group(0),
                    )
                )
                if pattern.id not in seen_ids:
                    seen_ids.add(pattern.id)
                    metas_in_order.append(pattern_meta(pattern.id))

    return matches, metas_in_order


__all__ = [
    "PATTERNS",
    "PatternDef",
    "PatternMatch",
    "Sentence",
    "detect_patterns",
    "pattern_meta",
]
