"""
Synchronous word-info lookup. Pinyin + meaning fallback chain that the
word-state mutators and the auto-enrol service use to populate snapshot
columns on UserWord at insert time.
"""

import pytest

from app.services.word_info import lookup_pinyin_meaning
from app.state import hsk_vocab, unknown_word_cache


@pytest.fixture
def hsk_chars():
    """A handful of single-char HSK entries we can compose into compounds."""
    original = dict(hsk_vocab)
    hsk_vocab.clear()
    hsk_vocab.update(
        {
            "我": {"pinyin": "wǒ", "meaning": "I", "level_new": "new-1"},
            "你": {"pinyin": "nǐ", "meaning": "you", "level_new": "new-1"},
            "好": {"pinyin": "hǎo", "meaning": "good", "level_new": "new-1"},
        }
    )
    yield
    hsk_vocab.clear()
    hsk_vocab.update(original)


def test_direct_hsk_entry(hsk_chars):
    pinyin, meaning = lookup_pinyin_meaning("我")
    assert pinyin == "wǒ"
    assert meaning == "I"


def test_compound_assembled_from_hsk_characters(hsk_chars):
    pinyin, meaning = lookup_pinyin_meaning("你好")
    assert "nǐ" in pinyin and "hǎo" in pinyin
    assert "you" in meaning and "good" in meaning
    assert " + " in meaning  # joined glosses


def test_unknown_word_cache_used_when_hsk_misses(hsk_chars):
    unknown_word_cache["道德"] = {"pinyin": "dào dé", "meaning": "virtue (cached)"}
    try:
        pinyin, meaning = lookup_pinyin_meaning("道德")
        assert pinyin == "dào dé"
        assert meaning == "virtue (cached)"
    finally:
        unknown_word_cache.pop("道德", None)


def test_pure_pypinyin_fallback_when_everything_else_misses(hsk_chars):
    # 龍 is not in our test hsk_vocab, not in the unknown cache.
    pinyin, meaning = lookup_pinyin_meaning("龍")
    assert pinyin  # pypinyin always produces something
    assert meaning == ""  # no gloss source -> empty


def test_empty_input_returns_empty():
    assert lookup_pinyin_meaning("") == ("", "")
    assert lookup_pinyin_meaning("   ") == ("", "")
