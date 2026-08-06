"""
`resolve_from_cedict` — regression coverage for a real bug found in the
bundled library: multi-character words jieba correctly segments as one
token (e.g. "一个", "变得") but that aren't themselves a key in `hsk_vocab`
used to fall through to `create_compound_from_hsk`'s per-character glue
("one + used in 自個兒|自个儿[zi4 ge3 r5]") — nonsense to a reader, and
easy to mistake for a segmentation bug rather than a lookup-priority one.
`resolve_from_cedict` must be checked (and win) before that glue fallback
whenever CC-CEDICT already has a proper entry for the whole word.
"""

import pytest

from app.services.segmentation import _needs_lookup
from app.services.word_lookup import resolve_from_cedict
from app.state import cedict_vocab, hsk_vocab


@pytest.fixture
def vocab():
    """Isolated hsk_vocab/cedict_vocab so this test doesn't depend on
    whatever a prior test session's startup event happened to download."""
    original_hsk = dict(hsk_vocab)
    original_cedict = dict(cedict_vocab)
    hsk_vocab.clear()
    hsk_vocab.update(
        {
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
        }
    )
    cedict_vocab.clear()
    cedict_vocab.update(
        {
            "一个": {"pinyin": "yī ge", "meaning": "a; an; one", "meanings": ["a; an; one"]},
            "变得": {"pinyin": "biàn de", "meaning": "to become", "meanings": ["to become"]},
        }
    )
    yield
    hsk_vocab.clear()
    hsk_vocab.update(original_hsk)
    cedict_vocab.clear()
    cedict_vocab.update(original_cedict)


def test_cedict_hit_wins_over_per_character_glue(vocab):
    """The bug: 一个's per-character glue ("one + used in 自個兒...") is
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


def test_needs_lookup_prefers_cedict_over_compound_glue(vocab):
    """End-to-end priority check: a segment that's both all-HSK-characters
    AND has a direct CEDICT entry must be routed to 'cedict', not
    'compound' — otherwise the dispatcher would still hit the glue path
    resolve_from_cedict was built to avoid."""
    assert _needs_lookup("一个") == "cedict"


def test_needs_lookup_falls_back_to_compound_without_cedict_entry(vocab):
    cedict_vocab.pop("一个", None)
    assert _needs_lookup("一个") == "compound"
