"""Pure-logic tests for the watch-and-read prototype's caption handling.

No network calls — extract_video_id and the sentence-merge logic are
plain string/list manipulation, so they're tested directly against
synthetic cues rather than hitting YouTube.
"""

import pytest

from app.services.youtube_captions import (
    _MAX_SENTENCE_CHARS,
    _MAX_SENTENCE_SECONDS,
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
    def test_manual_captions_merge_until_a_cap_or_the_sentence_ends(self):
        """
        Real manually-authored cues (this is an actual TED zh-Hans track) —
        cue boundaries follow line-length/timing, not sentence boundaries,
        so a cue with no closing punctuation correctly merges into the
        next. Here the second cue alone (17 chars) would push the combined
        block to 26 chars, over the 25-char cap, so the cap closes the
        first cue out on its own rather than gluing them together.
        """
        cues = [
            {"text": "我第一次看到园区时", "start": 0.2, "duration": 1.1},
            {"text": "觉得简直不可思议，这里有排球场地。", "start": 1.3, "duration": 2.6},
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 2
        assert sentences[0].text == "我第一次看到园区时"
        assert sentences[0].start == 0.2
        assert sentences[0].end == pytest.approx(1.3)
        assert sentences[1].text == "觉得简直不可思议，这里有排球场地。"
        assert sentences[1].start == pytest.approx(1.3)
        assert sentences[1].end == pytest.approx(3.9)

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

    def test_long_unpunctuated_single_cue_is_hard_chunked(self):
        """
        A single cue with no punctuation at all used to pass through
        whole regardless of length (merging can't split *within* a cue,
        only cap how many cues get glued together) — the hard-chunking
        tier in _split_cue_into_sentences now closes that gap too.
        """
        long_word = "字" * 70
        cues = [{"text": long_word, "start": 0.0, "duration": 1.0}]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) > 1
        assert all(len(s.text) <= _MAX_SENTENCE_CHARS for s in sentences)
        assert "".join(s.text for s in sentences) == long_word

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

    def test_comma_forces_an_early_split_with_no_terminal_punctuation(self):
        """
        Real-world regression: a fansubbed episode's "manually created"
        track had zero punctuation of any kind for long stretches, which
        let unrelated clauses glue into one 60+-char, 14s+ highlighted
        block. Treating a comma as a soft close (once the buffer already
        has content) fixes the common case where clauses ARE comma-
        separated even without a final full stop.
        """
        cues = [
            {"text": "你好，世界", "start": 0.0, "duration": 1.0},
            {"text": "这是下一句", "start": 1.0, "duration": 1.0},
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 2
        assert sentences[0].text == "你好，世界"
        assert sentences[1].text == "这是下一句"

    def test_char_cap_never_overshoots_across_multiple_cues(self):
        """
        The cap must be checked *before* appending, not after — checking
        after let a block grow to 31 chars against a 25-char cap, since by
        the time the overshoot was noticed the cue was already glued on.
        """
        cues = [{"text": "字" * 10, "start": float(i), "duration": 1.0} for i in range(5)]
        sentences = _merge_into_sentences(cues)
        assert all(len(s.text) <= 25 for s in sentences)

    def test_time_cap_forces_a_cut_across_a_long_silent_gap(self):
        """
        Real-world regression: a scene-change gap of ~170s between two
        cues with sparse text produced one sentence spanning 168 seconds,
        because only character count was capped. A short span of dialogue
        followed by a huge time jump must not be merged with what comes
        after it, even though the combined text is well under the char cap.
        """
        cues = [
            {"text": "你好", "start": 0.0, "duration": 1.0},
            {"text": "再见", "start": 170.0, "duration": 1.0},
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 2
        assert sentences[0].text == "你好"
        assert sentences[0].end == pytest.approx(1.0)
        assert sentences[1].text == "再见"
        assert sentences[1].start == pytest.approx(170.0)

    def test_backward_jumping_cues_are_dropped_not_merged(self):
        """
        Real-world regression: a fansubbed episode's caption track had a
        chunk of duplicate/corrupt cues jumping backward by hundreds of
        seconds partway through, which produced a sentence with
        end < start when trusted blindly.
        """
        cues = [
            {"text": "正常的对话", "start": 1410.0, "duration": 4.7},
            {"text": "损坏的重复数据", "start": 1053.259, "duration": 1.4},
            {"text": "更多损坏数据", "start": 21.97, "duration": 1.0},
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 1
        assert sentences[0].text == "正常的对话"
        assert sentences[0].end >= sentences[0].start

    def test_multi_sentence_cue_splits_with_proportional_timing(self):
        """
        Real-world regression: a Whisper/SRT segment (transcribe-
        orchestrator's ASR output) bundled two complete sentences into
        one multi-second block, since ASR timestamps only exist at the
        segment level — the highlight then lagged a full sentence behind
        the audio. A cue's own text must be split at real sentence-ending
        punctuation before the merge/cap logic ever sees it. Both
        sentences here are individually under the char cap, so this
        isolates the sentence-boundary tier itself — a case where one
        piece is still too long after this split is covered separately
        (test_partial_punctuation_still_escalates_the_leftover_remainder).
        """
        cues = [
            {
                "text": "我是佩琪，这是我弟弟乔治。这是我妈妈，这是我爸爸。",
                "start": 0.1,
                "duration": 10.0,
            },
        ]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 2
        assert sentences[0].text == "我是佩琪，这是我弟弟乔治。"
        assert sentences[1].text == "这是我妈妈，这是我爸爸。"
        # Proportional split: sentence 1 is 13 of the 25 total characters,
        # so it should get roughly (13/25) of the 10.0s span, not all of it.
        assert sentences[0].start == pytest.approx(0.1)
        assert sentences[0].end == pytest.approx(0.1 + 10.0 * 13 / 25, abs=0.05)
        assert sentences[1].end == pytest.approx(10.1)

    def test_single_sentence_cue_is_unaffected_by_the_split(self):
        cues = [{"text": "你好，世界！", "start": 0.0, "duration": 2.0}]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 1
        assert sentences[0].text == "你好，世界！"
        assert sentences[0].start == 0.0
        assert sentences[0].end == pytest.approx(2.0)

    def test_short_comma_only_cue_is_not_split(self):
        """
        A short cue with an internal comma but no final mark (a common,
        legitimate shape — e.g. a trailing clause cut off mid-thought)
        must not be chopped at the comma; only over-length/over-duration
        cues fall through to the comma tier.
        """
        cues = [{"text": "既然我们来到了郊外，我觉得", "start": 0.0, "duration": 3.0}]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) == 1
        assert sentences[0].text == "既然我们来到了郊外，我觉得"

    def test_long_comma_only_cue_falls_back_to_comma_split(self):
        """
        Real-world regression: a Peppa Pig dialogue line ran 21.5s/96
        chars on commas alone with zero terminal punctuation anywhere —
        the sentence-boundary tier alone left it as one giant block.
        """
        text = (
            "好的，等一下，佩奇，蔬菜皮不能直接扔进普通的垃圾桶，"
            "他们要扔进这个棕色的垃圾桶，香蕉，没错，乔治，那个就是香蕉皮，"
            "除此之外还有洋葱、胡萝卜和其他蔬菜削下来的皮都在里面，猪爷爷，猪奶奶会很喜欢的"
        )
        cues = [{"text": text, "start": 34.2, "duration": 21.5}]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) > 5
        assert all(len(s.text) <= _MAX_SENTENCE_CHARS for s in sentences)
        assert sentences[0].text == "好的，"
        assert sentences[0].start == pytest.approx(34.2)
        assert sentences[-1].end == pytest.approx(34.2 + 21.5)

    def test_partial_punctuation_still_escalates_the_leftover_remainder(self):
        """
        Real-world regression: a single cue carried two short, properly
        question-marked sentences followed by a 21.5s/96-char comma-only
        run-on — splitting once at the sentence-boundary tier produced 3
        pieces (>1), which short-circuited any further escalation before
        this was recursive, leaving that trailing remainder as one giant
        piece untouched.
        """
        text = (
            "要我帮忙吗？谢谢佩奇，你能把这些削下来的皮清理掉吗？"
            "好的，等一下，佩奇，蔬菜皮不能直接扔进普通的垃圾桶，"
            "他们要扔进这个棕色的垃圾桶，香蕉，没错，乔治，那个就是香蕉皮，"
            "除此之外还有洋葱、胡萝卜和其他蔬菜削下来的皮都在里面，猪爷爷，猪奶奶会很喜欢的"
        )
        cues = [{"text": text, "start": 28.33, "duration": 27.34}]
        sentences = _merge_into_sentences(cues)
        assert sentences[0].text == "要我帮忙吗？"
        assert sentences[1].text == "谢谢佩奇，你能把这些削下来的皮清理掉吗？"
        assert all(len(s.text) <= _MAX_SENTENCE_CHARS for s in sentences)
        assert "".join(s.text for s in sentences) == text
        assert sentences[0].start == pytest.approx(28.33)
        assert sentences[-1].end == pytest.approx(28.33 + 27.34)

    def test_punctuation_free_cue_falls_back_to_hard_chunking(self):
        """
        Real-world regression: sung dialogue ran 23.7s/52 chars with
        *zero* punctuation of any kind (no commas, no full stops) —
        neither the sentence nor comma tier can split this at all, so
        the last-resort character-count chunker has to engage. Chunk
        count must satisfy both caps: this text is well under the char
        cap in total but badly exceeds the time cap (slow singing), so
        char-count alone (round(52/25)=2 chunks of ~12s each) wouldn't
        have been enough on its own.
        """
        text = "一条蚯蚓虫子 虫子你是小虫子你是小虫子你好吗我爱你你是小虫子干得好你要做条好虫子哦把这些都变成堆肥哦好吗"
        cues = [{"text": text, "start": 165.9, "duration": 23.7}]
        sentences = _merge_into_sentences(cues)
        assert len(sentences) >= 3
        assert all((s.end - s.start) <= _MAX_SENTENCE_SECONDS + 0.5 for s in sentences)
        assert "".join(s.text for s in sentences) == text
        assert sentences[0].start == pytest.approx(165.9)
        assert sentences[-1].end == pytest.approx(165.9 + 23.7)
