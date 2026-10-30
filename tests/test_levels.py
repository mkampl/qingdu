"""Tests for the HSK level parser and the level-estimation function."""

from app.services.levels import estimate_text_level, level_number


def test_empty_text_returns_unknown():
    assert estimate_text_level({}, 0) == "Unknown"


def test_all_hsk1_returns_hsk1():
    assert estimate_text_level({"hsk1": 10}, 10) == "HSK 1"


def test_mixed_distribution_crosses_threshold_at_hsk2():
    # With 80% threshold (default in constants), 8 of 10 covered by HSK1+HSK2.
    result = estimate_text_level({"hsk1": 5, "hsk2": 3, "hsk5": 2}, 10)
    assert result == "HSK 2"


def test_beyond_hsk9():
    # 100 words all at HSK10+ — function returns "HSK 9+".
    assert estimate_text_level({}, 100) == "HSK 9+"


def test_level_number_new_spellings():
    assert level_number("new-1") == 1
    assert level_number("new-6") == 6
    assert level_number("new-7") == 7
    assert level_number("new-7+") == 7
    assert level_number("new-7-9") == 7
    assert level_number("new-9") == 9


def test_level_number_prefix_choice():
    assert level_number("old-6") is None
    assert level_number("old-6", ("new-", "old-")) == 6
    assert level_number("new-3", ("old-",)) is None
    assert level_number("newest-7") is None
    assert level_number("newest-7", ("newest-",)) == 7
    assert level_number("7-9", ("",)) == 7
    assert level_number("7", ("",)) == 7
    assert level_number("3", ("",)) == 3
    assert level_number("3") is None
    assert level_number("new-3", ("new-", "")) == 3


def test_level_number_rejects_other_input():
    for level in (None, "", "unknown", "Custom", "new-", "new-0", "new-10", "new-3+", "new-3x"):
        assert level_number(level) is None, level
    assert level_number(7) is None
    assert level_number("new-8-9") is None
