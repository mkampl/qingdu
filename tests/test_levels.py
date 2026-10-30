"""Tests for the HSK level parser and the level-estimation function."""

from app.services.levels import estimate_text_level, hsk_statistics, level_number


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


def test_hsk_statistics_counts_both_systems():
    stats = hsk_statistics(
        [
            ("new-1", "old-1"),
            ("new-1", None),
            ("new-7-9", "old-7"),  # old-7 has no bucket but counts in the total
            ("3", "2"),  # bare legacy levels
            (None, "old-6"),
            ("unknown", ""),
        ]
    )
    assert stats["hsk_words_new"] == 4
    assert stats["hsk_distribution_new"] == {
        "hsk1": 2,
        "hsk2": 0,
        "hsk3": 1,
        "hsk4": 0,
        "hsk5": 0,
        "hsk6": 0,
        "hsk7": 1,
        "hsk8": 0,
        "hsk9": 0,
    }
    assert stats["hsk_words_old"] == 4
    assert stats["hsk_distribution_old"] == {
        "hsk1": 1,
        "hsk2": 1,
        "hsk3": 0,
        "hsk4": 0,
        "hsk5": 0,
        "hsk6": 1,
    }
    assert stats["estimated_level_new"] == estimate_text_level(stats["hsk_distribution_new"], 4)
    assert stats["hsk_words"] == 4
    assert stats["hsk_distribution"] is stats["hsk_distribution_new"]
    assert stats["estimated_level"] == stats["estimated_level_new"]


def test_hsk_statistics_empty():
    stats = hsk_statistics([])
    assert stats["hsk_words_new"] == stats["hsk_words_old"] == 0
    assert stats["estimated_level_new"] == stats["estimated_level_old"] == "Unknown"
    assert list(stats) == [
        "hsk_words_new",
        "hsk_distribution_new",
        "estimated_level_new",
        "hsk_words_old",
        "hsk_distribution_old",
        "estimated_level_old",
        "hsk_words",
        "hsk_distribution",
        "estimated_level",
    ]
