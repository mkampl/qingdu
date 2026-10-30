"""Segmentation never yields phrases that are not words.

jieba (with its HMM) produces tokens such as 我来, 很多, 三个 or 洗衣服 that
no dictionary lists; the reader would then glue per-character glosses
together ("very + many") or ask a translation service about the isolated
token. Tokens are dictionary words (HSK, CC-CEDICT, the user's glossary) or
single characters. Runs against the pinned dictionary data.
"""

import asyncio
import json
from pathlib import Path

import pytest

from app.services import lexicon, translation
from app.services.segmentation import analyze_chinese_text, prime_jieba, segment_text

LIBRARY_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "library"


@pytest.fixture(scope="module")
def segmenter(pinned_dictionaries):
    """Pinned dictionaries plus jieba primed with the HSK words, as at startup."""
    prime_jieba()


def _cjk_tokens(tokens):
    return [t for t in tokens if t != "\n"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("我来了", ["我", "来", "了"]),
        ("他有很多书", ["他", "有", "很", "多", "书"]),
        ("他买了三个。", ["他", "买", "了", "三", "个", "。"]),
        ("第三天", ["第", "三", "天"]),
        ("我洗衣服", ["我", "洗", "衣服"]),
        ("他坐在椅子上", ["他", "坐", "在", "椅子", "上"]),
        ("天气太热", ["天气", "太", "热"]),
        ("这次很好", ["这", "次", "很", "好"]),
        ("第一个", ["第一", "个"]),
    ],
)
def test_report_tokens_are_split(segmenter, text, expected):
    assert segment_text(text) == expected


@pytest.mark.parametrize("word", ["大卫", "山本", "一个", "第一", "衣服", "不想"])
def test_dictionary_words_stay_whole(segmenter, word):
    assert word in segment_text(f"{word}。")


def test_glossary_word_stays_whole(segmenter):
    glossary = {"洗衣服": {"meaning": "to do the laundry"}}
    assert segment_text("我洗衣服", glossary) == ["我", "洗衣服"]


def test_glossary_term_jieba_cuts_up_is_joined(segmenter):
    glossary = {"抱元守一": {"meaning": "embracing the origin, guarding the One"}}
    assert "抱元守一" not in segment_text("要抱元守一。")
    assert segment_text("要抱元守一。", glossary) == ["要", "抱元守一", "。"]


def test_longest_glossary_term_wins(segmenter):
    glossary = {"三功": {"meaning": "a"}, "三功九秘": {"meaning": "b"}}
    assert "三功九秘" in segment_text("修三功九秘。", glossary)


def test_glossary_term_does_not_cut_through_a_token(segmenter):
    # 我们 is one token; a glossary term 们修 must not split it.
    glossary = {"们修": {"meaning": "x"}}
    assert "我们" in segment_text("我们修道。", glossary)


def test_line_breaks_are_kept(segmenter):
    assert segment_text("很多\n三个") == ["很", "多", "\n", "三", "个"]


def test_split_prefers_hsk_words_and_known_sub_words(segmenter):
    assert lexicon.split_into_known("洗衣服") == ["洗", "衣服"]
    assert lexicon.split_into_known("很漂亮") == ["很", "漂亮"]
    assert lexicon.split_into_known("衣服") == ["衣服"]
    assert lexicon.split_into_known("") == []


def test_every_library_token_is_a_word(segmenter):
    """Across all bundled library texts, every multi-character Chinese
    token is a dictionary word."""
    bad = {}
    for path in sorted(LIBRARY_DIR.rglob("*.json")):
        text = json.loads(path.read_text(encoding="utf-8"))["text"]
        for token in _cjk_tokens(segment_text(text)):
            if len(token) > 1 and lexicon.is_cjk_word(token) and not lexicon.in_dictionary(token):
                bad[token] = path.name
    assert bad == {}


def test_analysis_makes_no_word_level_translation_calls(segmenter, monkeypatch):
    async def _boom(*args, **kwargs):
        raise AssertionError("isolated token sent to a translation service")

    monkeypatch.setattr(translation, "get_translation_with_source", _boom)
    result = asyncio.run(analyze_chinese_text("我来洗衣服。iPhone很多。林月来了。"))
    words = [w for w in result["words"] if w["text"] != "\n"]
    assert all(" + " not in (w["meaning"] or "") for w in words)
    texts = [w["text"] for w in words]
    assert "衣服" in texts and "很多" not in texts and "我来" not in texts
    latin = next(w for w in words if w["text"] == "iPhone")
    assert latin["is_hsk"] is False
    assert not latin["meaning"]
