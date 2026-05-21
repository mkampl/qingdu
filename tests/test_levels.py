"""Tests for the pure level-estimation function."""

from app.services.levels import estimate_text_level


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
