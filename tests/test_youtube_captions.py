"""Pure-logic tests for the watch-and-read prototype's caption handling.

No network calls — extract_video_id and the sentence-merge logic are
plain string/list manipulation, so they're tested directly against
synthetic cues rather than hitting YouTube.
"""

import pytest

from app.services.youtube_captions import (
    YoutubeCaptionError,
    _merge_into_sentences,
    extract_video_id,
)


class TestExtractVideoId:
    def test_bare_id(self):
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PL123"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_garbage_raises(self):
        with pytest.raises(YoutubeCaptionError):
            extract_video_id("not a url at all")

    def test_wrong_length_id_raises(self):
        with pytest.raises(YoutubeCaptionError):
            extract_video_id("tooshort")


class TestMergeIntoSentences:
    def test_manual_captions_merge_until_the_sentence_actually_ends(self):
        """
        Real manually-authored cues (this is an actual TED zh-Hans track) —
        cue boundaries follow line-length/timing, not sentence boundaries,
        so a cue with no closing punctuation correctly merges into the next.
        """
        cues = [
            {"text": "我第一次看到园区时", "start": 0.2, "duration": 1.1},
            {"text": "觉得简直不可思议，这里有排球场地。", "start": 1.3, "duration": 2.6},
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 1
        assert sentences[0].text == "我第一次看到园区时觉得简直不可思议，这里有排球场地。"
        assert sentences[0].start == 0.2
        assert sentences[0].end == pytest.approx(3.9)

    def test_manual_captions_close_out_a_cue_that_ends_the_sentence(self):
        cues = [
            {"text": "你好。", "start": 0.0, "duration": 0.5},
            {"text": "再见。", "start": 0.5, "duration": 0.5},
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 2
        assert sentences[0].text == "你好。"
        assert sentences[1].text == "再见。"

    def test_unpunctuated_asr_cues_get_glued_until_a_sentence_end(self):
        cues = [
            {"text": "你好", "start": 0.0, "duration": 0.5},
            {"text": "今天天气", "start": 0.5, "duration": 0.5},
            {"text": "怎么样。", "start": 1.0, "duration": 0.5},
            {"text": "我们出去玩吧", "start": 1.5, "duration": 0.5},
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 2
        assert sentences[0].text == "你好今天天气怎么样。"
        assert sentences[0].start == 0.0
        assert sentences[0].end == pytest.approx(1.5)
        # Trailing unfinished cue still gets flushed at the end.
        assert sentences[1].text == "我们出去玩吧"

    def test_long_unpunctuated_run_is_cut_by_the_length_cap(self):
        long_word = "字" * 70
        cues = [{"text": long_word, "start": 0.0, "duration": 1.0}]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 1
        assert sentences[0].text == long_word

    def test_empty_cues_are_skipped(self):
        cues = [
            {"text": "", "start": 0.0, "duration": 0.1},
            {"text": "你好。", "start": 0.1, "duration": 0.5},
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 1
        assert sentences[0].text == "你好。"

    def test_empty_input_returns_empty_list(self):
        assert _merge_into_sentences([]) == []
