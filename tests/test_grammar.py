"""
Grammar-pattern detector — verify each pattern fires on its canonical
example, doesn't fire on negatives, and that detect_patterns reports
correct absolute word indexes across multi-sentence inputs.
"""

import jieba
import pytest

from app.services.grammar import (
    PATTERNS,
    Sentence,
    detect_patterns,
    pattern_meta,
)
from app.services.segmentation import _group_sentences, segment_text

# A private tokenizer: other tests add words to jieba's global one.
_TOKENIZER = jieba.Tokenizer()


def _sentence(text: str) -> Sentence:
    """Build a Sentence from raw text, cut by jieba's default dictionary."""
    return Sentence(words=_TOKENIZER.lcut(text), text=text)


def _detect_one(text: str) -> set[str]:
    """Convenience: return the set of pattern ids that fired on `text`."""
    matches, _ = detect_patterns([(0, _sentence(text))])
    return {m.pattern_id for m in matches}


def test_every_pattern_fires_on_its_example():
    """Each registered pattern should detect its own example sentence."""
    for p in PATTERNS:
        ids = _detect_one(p.example)
        assert p.id in ids, (
            f"Pattern {p.id} ({p.title}) failed to fire on its own example "
            f"{p.example!r} — detected only {ids}"
        )


def test_shi_de_ignores_bare_yes_construction():
    # "是的" by itself is just "yes" — no emphasis structure between them.
    ids = _detect_one("是的。")
    assert "shi-de" not in ids


def test_yue_yue_matches_both_separated_and_collocated_forms():
    """越来越 (collocated) and 越X越Y (separated) are the same construction."""
    assert "yue-yue" in _detect_one("天气越来越冷。")
    assert "yue-yue" in _detect_one("我越想越生气。")
    # No 越 at all — no match.
    assert "yue-yue" not in _detect_one("我很高兴。")


def test_yinwei_suoyi_requires_both_halves():
    only_yinwei = _detect_one("因为下雨,我没去。")
    assert "yinwei-suoyi" not in only_yinwei, (
        "half-match shouldn't fire — keeps the panel signal high"
    )
    full = _detect_one("因为下雨,所以我没去。")
    assert "yinwei-suoyi" in full


def test_absolute_offsets_span_multiple_sentences():
    """
    The detector returns absolute word indexes. When we hand it two sentences
    with explicit base offsets, the spans for the second one must be
    higher than the first.
    """
    s1 = _sentence("我是昨天来的。")  # contains 是…的
    s2 = _sentence("天气越来越冷。")  # contains 越…越
    matches, _ = detect_patterns([(0, s1), (len(s1.words), s2)])
    by_id = {m.pattern_id: m for m in matches}
    assert "shi-de" in by_id
    assert "yue-yue" in by_id
    assert by_id["yue-yue"].start_word_idx >= len(s1.words)


def test_group_sentences_line_breaks():
    tokens = ["我", "好", "\n", "你", "好", "。", "他"]
    grouped = [(start, s.words) for start, s in _group_sentences(tokens)]
    assert grouped == [(0, ["我", "好"]), (3, ["你", "好", "。"]), (6, ["他"])]
    grouped = [(start, s.words) for start, s in _group_sentences(tokens, split_lines=False)]
    assert grouped == [(0, ["我", "好", "\n", "你", "好", "。"]), (6, ["他"])]


def test_pattern_meta_round_trip():
    meta = pattern_meta("shi-de")
    assert meta["id"] == "shi-de"
    assert meta["title"]
    assert meta["explanation"]
    assert meta["example"]


def test_metas_returned_once_per_unique_pattern():
    """Two sentences both containing 越…越 produce two matches but only one meta."""
    s1 = _sentence("天气越来越冷。")
    s2 = _sentence("我越想越生气。")
    sentences = [(0, s1), (len(s1.words), s2)]
    matches, metas = detect_patterns(sentences)
    yue_metas = [m for m in metas if m["id"] == "yue-yue"]
    assert len(yue_metas) == 1
    yue_matches = [m for m in matches if m.pattern_id == "yue-yue"]
    assert len(yue_matches) == 2


# --- Markers that are also parts of ordinary words ------------------------------


def _ids(text: str) -> list[str]:
    matches, _ = detect_patterns(_group_sentences(segment_text(text)))
    return [m.pattern_id for m in matches]


@pytest.mark.parametrize(
    ("text", "pattern", "expected"),
    [
        ("他跑得很快。", "de-resultative", True),
        ("我觉得很好。", "de-resultative", False),
        ("道亦得之。", "de-resultative", False),
        ("但得一元神。", "de-resultative", False),
        ("我把书放下了。", "ba", True),
        ("一把椅子。", "ba", False),
        ("我把握机会。", "ba", False),
        ("他被打了。", "bei", True),
        ("被子很暖和。", "bei", False),
        ("他比我高。", "bi-comparison", True),
        ("比较好。", "bi-comparison", False),
        ("我去过北京。", "guo-experiential", True),
        ("过去的事。", "guo-experiential", False),
        ("他看着我。", "zhe-durative", True),
        ("我很着急。", "zhe-durative", False),
        ("他吃了饭。", "le-aspect", True),
        ("我了解他。", "le-aspect", False),
    ],
)
def test_marker_must_be_the_grammar_word(text, pattern, expected):
    assert (pattern in _ids(text)) is expected
