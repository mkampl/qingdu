"""
Chunk-splitting for long-sentence TTS. The actual HTTP fetch isn't covered
here (Google Translate); we just verify the splitter respects the cap,
honors punctuation, and handles edge cases.
"""

from app.services.tts import _MAX_CHARS_PER_REQUEST, _split_for_tts


def test_short_text_returns_one_chunk():
    text = "你好,世界。"
    chunks = _split_for_tts(text)
    assert chunks == [text]


def test_long_text_respects_cap():
    text = "中文。" * 80  # 240 chars
    chunks = _split_for_tts(text)
    assert len(chunks) >= 2
    assert all(len(c) <= _MAX_CHARS_PER_REQUEST for c in chunks)
    # Reassembly is lossless.
    assert "".join(chunks) == text


def test_split_prefers_punctuation_boundary():
    # Two clauses; the splitter should keep each clause intact.
    clause = "我今天去学校学习中文,老师教我们很多新的汉字" * 3 + "。"
    chunks = _split_for_tts(clause)
    # Every chunk except possibly the last should end with sentence-level
    # punctuation (chosen from the splitter's set).
    enders = set(",，。！？；：、,.!?;:")
    for c in chunks[:-1]:
        assert c[-1] in enders, f"chunk {c!r} doesn't end at punctuation"


def test_pathological_long_run_hard_slices():
    # 500 chars with no punctuation at all — splitter must still bound chunks.
    text = "中" * 500
    chunks = _split_for_tts(text)
    assert len(chunks) >= 3
    assert all(len(c) <= _MAX_CHARS_PER_REQUEST for c in chunks)
    assert "".join(chunks) == text
