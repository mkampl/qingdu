"""
Pronunciation-assessment service — pure-function pieces.

We don't exercise faster-whisper or librosa.pyin here; both pull
heavy ML/native deps and a real audio sample would dwarf the rest
of the test suite. The interesting logic is:
  - tone extraction from tone-marked pinyin
  - resampling + 0..1 normalisation of a noisy F0 contour
  - shape comparison (does a "rising" observation score higher
    against tone 2 than against tone 4?)
"""

import numpy as np
import pytest

from app.services import pronounce


def test_tone_from_pinyin_first_tone():
    assert pronounce._tone_from_pinyin("mā") == 1
    assert pronounce._tone_from_pinyin("dī") == 1


def test_tone_from_pinyin_second_to_fourth():
    assert pronounce._tone_from_pinyin("má") == 2
    assert pronounce._tone_from_pinyin("mǎ") == 3
    assert pronounce._tone_from_pinyin("mà") == 4


def test_tone_from_pinyin_neutral_when_no_mark():
    assert pronounce._tone_from_pinyin("ma") == 5
    assert pronounce._tone_from_pinyin("") == 5
    assert pronounce._tone_from_pinyin("le") == 5


def test_strip_punctuation_removes_chinese_and_western_marks():
    assert pronounce._strip_punctuation("你好，世界。") == "你好世界"
    assert pronounce._strip_punctuation("Hello, world!") == "Helloworld"


def test_resample_contour_handles_nans():
    """librosa.pyin emits NaN for unvoiced frames — those must be
    masked out before interpolation rather than poisoning every
    resampled value."""
    contour = np.array([100.0, np.nan, 150.0, np.nan, 200.0])
    out = pronounce._resample_contour(contour, n=5)
    assert out.shape == (5,)
    assert not np.any(np.isnan(out))
    # Voiced values present at the endpoints carry through.
    assert out[0] == pytest.approx(100.0, abs=1e-6)
    assert out[-1] == pytest.approx(200.0, abs=1e-6)


def test_resample_contour_returns_zeros_for_no_voicing():
    """All-NaN input means we heard no voiced audio in the syllable
    window — score it as 0 instead of garbage."""
    contour = np.array([np.nan, np.nan, np.nan, np.nan])
    assert np.array_equal(pronounce._resample_contour(contour, n=5), np.zeros(5))


def test_normalize_01_collapses_flat_input_to_zeros():
    # A perfectly flat contour has zero span — keep the scorer numerically
    # honest by treating it as "no shape" rather than dividing by zero.
    assert np.array_equal(pronounce._normalize_01(np.array([1.0, 1.0, 1.0])), np.zeros(3))


def test_score_tone_rewards_correct_shape_over_wrong_shape():
    """A rising observed contour should score much higher against
    tone 2 ("rising") than against tone 4 ("falling")."""
    rising = np.linspace(80, 200, 50)  # monotonic rise
    rising_score = pronounce._score_tone(rising, expected_tone=2)
    falling_match_score = pronounce._score_tone(rising, expected_tone=4)
    assert rising_score > 0.7
    assert falling_match_score < rising_score / 2


def test_score_tone_zero_when_no_signal():
    contour = np.full(10, np.nan)
    assert pronounce._score_tone(contour, expected_tone=1) == 0.0
