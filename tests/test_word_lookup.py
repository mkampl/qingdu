"""
`resolve_from_cedict` for multi-character words jieba segments as one
token (e.g. "一个", "变得") but that aren't themselves a key in `hsk_vocab`.
They must not fall through to `create_compound_from_hsk`'s per-character
glue ("one + used in 自個兒|自个儿[zi4 ge3 r5]"), which is nonsense to a
reader: `resolve_from_cedict` is checked (and wins) before that fallback
whenever CC-CEDICT has a proper entry for the whole word.
"""

import pytest

from app.services.segmentation import _resolve_non_hsk
from app.services.word_lookup import describe_non_word, resolve_from_cedict
from app.state import cedict_variants, cedict_vocab


@pytest.fixture
def vocab(swap_dictionaries):
    """Isolated hsk_vocab/cedict_vocab so this test doesn't depend on
    whatever another test left in the shared dictionaries."""
    swap_dictionaries(
        hsk={
            "一": {
                "pinyin": "yī",
                "meaning": "one",
                "level_new": "new-1",
                "level_old": "old-1",
            },
            "个": {
                "pinyin": "gě",
                "meaning": "used in 自個兒|自个儿[zi4 ge3 r5]",
                "level_new": "new-1",
                "level_old": "old-1",
            },
            "变": {"pinyin": "biàn", "meaning": "to change", "level_new": "new-2"},
        },
        cedict={
            "一个": {"pinyin": "yī ge", "meaning": "a; an; one", "meanings": ["a; an; one"]},
            "变得": {"pinyin": "biàn de", "meaning": "to become", "meanings": ["to become"]},
        },
        variants={},
    )


def test_cedict_hit_wins_over_per_character_glue(vocab):
    """一个's per-character glue ("one + used in 自個兒...") is
    strictly worse than CEDICT's own entry for the whole word."""
    info = resolve_from_cedict("一个")
    assert info is not None
    assert info["meaning"] == "a; an; one"
    assert info["pinyin"] == "yī ge"
    assert info["translation_source"] == "cedict"
    assert "自個兒" not in info["meaning"]


def test_cedict_hit_still_carries_hsk_level_when_all_chars_are_hsk(vocab):
    """Every character of 一个 is in hsk_vocab, so the reader should still
    colour it by HSK level even though the meaning comes from CEDICT."""
    info = resolve_from_cedict("一个")
    assert info["level_new"] == "new-1"
    assert info["level_old"] == "old-1"


def test_cedict_hit_without_full_hsk_coverage_has_no_level(vocab):
    """变得 — 得 isn't in this test's hsk_vocab, so it's not eligible for
    HSK colouring; the CEDICT meaning should still win, just uncoloured."""
    info = resolve_from_cedict("变得")
    assert info["meaning"] == "to become"
    assert info["level_new"] is None
    assert info["level_old"] is None


def test_no_cedict_entry_returns_none(vocab):
    assert resolve_from_cedict("不存在的词") is None


def test_resolver_prefers_cedict_entry(vocab):
    """A segment that is all HSK characters AND has a CEDICT entry gets the
    CEDICT gloss, never a per-character breakdown."""
    info = _resolve_non_hsk(["一个"], {})["一个"]
    assert info["translation_source"] == "cedict"
    assert info["meaning"] == "a; an; one"


def test_non_word_gets_parts_not_a_glued_meaning(vocab):
    cedict_vocab.pop("一个", None)
    info = _resolve_non_hsk(["一个"], {})["一个"]
    assert info["translation_source"] == "parts"
    assert info["meaning"] == ""
    assert info["meanings"] == []
    assert [p["word"] for p in info["parts"]] == ["一", "个"]
    assert info["parts"][0]["meaning"] == "one"
    # Still coloured by its characters' HSK level.
    assert info["level_new"] == "new-1"


def test_resolver_skips_hsk_and_glossary_words(vocab):
    glossary = {"道德": {"meaning": "virtue"}}
    assert _resolve_non_hsk(["一", "变", "\n", "道德"], glossary) == {}


def test_describe_non_word_ignores_non_chinese_tokens(vocab):
    assert describe_non_word("iPhone") is None


def test_single_character_outside_hsk_gets_its_cedict_entry(vocab):
    cedict_vocab["喵"] = {"pinyin": "miāo", "meaning": "meow", "meanings": ["meow"]}
    info = _resolve_non_hsk(["喵", "！"], {})
    assert info["喵"]["meaning"] == "meow"
    assert info["！"] is None


def test_variant_form_reads_its_headword(vocab):
    """玅 is listed in CC-CEDICT only as the traditional form of 妙."""
    cedict_vocab["妙"] = {"pinyin": "miào", "meaning": "clever", "meanings": ["clever"]}
    cedict_variants["玅"] = "妙"
    info = resolve_from_cedict("玅")
    assert info["meaning"] == "clever"
    assert info["pinyin"] == "miào"
    assert info["meaning_tags"] == ["variant of 妙"]
