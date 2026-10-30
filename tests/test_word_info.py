"""
Synchronous word-info lookup. Pinyin + meaning fallback chain that the
word-state mutators and the auto-enrol service use to populate snapshot
columns on UserWord at insert time.
"""

import pytest

from app.services.word_info import lookup_pinyin_meaning, word_parts


@pytest.fixture
def hsk_chars(swap_dictionaries):
    """A handful of single-char HSK entries we can compose into compounds.

    Also clears cedict_vocab for the duration of the test: entries
    another test left there (e.g. 你好 / 道德) would short-circuit the
    lookup chain before the fallback paths these tests exercise.
    """
    swap_dictionaries(
        hsk={
            "我": {"pinyin": "wǒ", "meaning": "I", "level_new": "new-1"},
            "你": {"pinyin": "nǐ", "meaning": "you", "level_new": "new-1"},
            "好": {"pinyin": "hǎo", "meaning": "good", "level_new": "new-1"},
        },
        cedict={},
    )


def test_direct_hsk_entry(hsk_chars):
    pinyin, meaning = lookup_pinyin_meaning("我")
    assert pinyin == "wǒ"
    assert meaning == "I"


def test_non_dictionary_compound_gets_no_glued_meaning(hsk_chars):
    """你好 is not in this test's dictionaries: the reading comes from
    pypinyin and the meaning stays empty instead of "you + good"."""
    pinyin, meaning = lookup_pinyin_meaning("你好")
    assert "nǐ" in pinyin and "hǎo" in pinyin
    assert meaning == ""


def test_word_parts_lists_known_sub_words(hsk_chars):
    assert word_parts("我好") == [
        {"word": "我", "pinyin": "wǒ", "meaning": "I"},
        {"word": "好", "pinyin": "hǎo", "meaning": "good"},
    ]
    assert word_parts("我") == []
    assert word_parts("") == []


def test_pure_pypinyin_fallback_when_everything_else_misses(hsk_chars):
    # 龍 is not in our test hsk_vocab.
    pinyin, meaning = lookup_pinyin_meaning("龍")
    assert pinyin  # pypinyin always produces something
    assert meaning == ""  # no gloss source -> empty


def test_empty_input_returns_empty():
    assert lookup_pinyin_meaning("") == ("", "")
    assert lookup_pinyin_meaning("   ") == ("", "")
