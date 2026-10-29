"""
YouTube caption fetch + sentence-merge for watch-and-read.

Pulls a Chinese caption track for a public YouTube video via the public
`timedtext` endpoint the YouTube player itself uses — no API key. (The
Data API v3 `captions.download` endpoint needs OAuth as the video's own
channel owner, so it can't read third-party videos.)

Manually-authored caption tracks are already real, punctuated sentences
and need no further work. Auto-generated (ASR) Chinese tracks are almost
always one long unpunctuated word stream, so those get re-segmented here
by merging consecutive cues until we hit sentence-ending punctuation or a
length cap.

YouTube blocks some requests from cloud/datacenter IP ranges. Callers
should cache aggressively (a video's captions never change), so a block
costs one failed fetch instead of breaking every later view.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    YouTubeTranscriptApi,
)

logger = logging.getLogger(__name__)

# Real (manually-authored) Chinese captions are tried in this order before
# we ever fall back to auto-generated ASR captions for any of them.
_PREFERRED_LANGS = ["zh-Hans", "zh-CN", "zh", "zh-Hant", "zh-TW", "zh-HK"]

# Terminal punctuation always closes a sentence. Commas/enumeration
# commas also close one: captions rarely carry a full stop mid-narration,
# and without this unrelated clauses glue into one long highlighted block.
# Cuts only fall at cue boundaries, so a comma cue still ends on a
# complete clause.
_SENTENCE_END = "。！？!?…，、"
_MAX_SENTENCE_CHARS = 25
# A track can carry no punctuation at all and have long silent gaps
# between cues, where few characters span minutes. This time cap forces a
# cut regardless of character count once a block runs long.
_MAX_SENTENCE_SECONDS = 8.0
_MAX_CUES = 400  # guards against multi-hour videos blowing up the analysis pass

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YoutubeCaptionError(Exception):
    """Raised when a video can't be resolved to a usable Chinese transcript."""


@dataclass
class CaptionSentence:
    start: float
    end: float
    text: str


def extract_video_id(url_or_id: str) -> str:
    """Accept a bare 11-char video ID or any common YouTube URL shape."""
    candidate = url_or_id.strip()
    if _VIDEO_ID_RE.match(candidate):
        return candidate

    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()

    if host == "youtu.be":
        vid = parsed.path.lstrip("/")
        if _VIDEO_ID_RE.match(vid):
            return vid
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            vid = parse_qs(parsed.query).get("v", [""])[0]
            if _VIDEO_ID_RE.match(vid):
                return vid
        for prefix in ("/embed/", "/shorts/", "/live/"):
            if parsed.path.startswith(prefix):
                vid = parsed.path[len(prefix) :].split("/")[0]
                if _VIDEO_ID_RE.match(vid):
                    return vid

    raise YoutubeCaptionError(f"Couldn't find a video ID in {url_or_id!r}.")


def _fetch_raw_cues(video_id: str) -> tuple[list[dict], bool]:
    """Return (cues, is_generated) for the best available Chinese track."""
    api = YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
    except CouldNotRetrieveTranscript as e:
        raise YoutubeCaptionError(f"Couldn't read captions for this video: {e}") from e

    try:
        transcript = transcript_list.find_manually_created_transcript(_PREFERRED_LANGS)
    except NoTranscriptFound:
        try:
            transcript = transcript_list.find_generated_transcript(_PREFERRED_LANGS)
        except NoTranscriptFound as e:
            raise YoutubeCaptionError(
                "This video has no Chinese caption track (manual or auto-generated)."
            ) from e

    try:
        fetched = transcript.fetch()
    except CouldNotRetrieveTranscript as e:
        raise YoutubeCaptionError(f"Couldn't fetch the caption track: {e}") from e

    cues = [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]
    return cues, transcript.is_generated


_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?…])")
_COMMA_BOUNDARY = re.compile(r"(?<=[，、,])")


def _is_too_big(text: str, full_len: int, full_duration: float) -> bool:
    """Is `text` (a piece of some larger original text) over either cap?
    Its duration is estimated proportionally from the original cue's
    total duration, since only the *original* cue carries a real
    timestamp — a piece's own duration is never independently known."""
    est_duration = full_duration * len(text) / full_len if full_len else 0.0
    return len(text) > _MAX_SENTENCE_CHARS or est_duration > _MAX_SENTENCE_SECONDS


def _split_text(text: str, full_len: int, full_duration: float) -> list[str]:
    """
    Recursively split `text` into pieces, escalating through three
    tiers, each engaged only where the previous one didn't produce a
    split *and* the text is still over-length/over-duration (so a short,
    legitimately single sentence like "你好，世界" that merely contains
    an internal comma is never chopped up):
      1. real terminal punctuation (。！？!?…) — always tried first.
      2. commas/enumeration commas — for run-on lines with no full stop.
      3. hard character/duration-based chunking — last resort for
         content with no punctuation at all (sung lyrics, for example).
         Not a real sentence boundary, just a cap on how long one
         highlight can run. Chunk count satisfies both caps, since
         drawn-out singing can exceed the time cap on very few
         characters.

    Recursive rather than one flat pass: a cue can carry some terminal
    punctuation and still leave a too-long comma-only remainder, which
    the next tier then splits.
    """
    if not _is_too_big(text, full_len, full_duration):
        return [text]

    parts = [p for p in _SENTENCE_BOUNDARY.split(text) if p.strip()]
    if len(parts) <= 1:
        parts = [p for p in _COMMA_BOUNDARY.split(text) if p.strip()]
    if len(parts) <= 1:
        est_duration = full_duration * len(text) / full_len if full_len else 0.0
        n_chars = -(-len(text) // _MAX_SENTENCE_CHARS)  # ceil division
        n_time = -(-int(est_duration) // int(_MAX_SENTENCE_SECONDS))
        n = max(1, n_chars, n_time)
        chunk_size = -(-len(text) // n)
        parts = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    if len(parts) <= 1:
        return [text]  # couldn't split further (e.g. a single character)
    return [piece for p in parts for piece in _split_text(p, full_len, full_duration)]


def _split_cue_into_sentences(cue: dict) -> list[dict]:
    """
    Split one cue's own text into sub-cues, distributing its [start, end]
    span proportionally by character count. A cue that's already within
    both caps comes back unchanged.

    Needed for Whisper/SRT-sourced cues: ASR timestamps only exist at the
    segment level, and a segment often bundles several sentences into one
    multi-second block, so the highlight would lag behind the audio.
    There's no per-sentence timing, so this is a proportional-by-length
    approximation. A no-op for ordinary YouTube caption cues, which are
    usually single clauses already.
    """
    parts = _split_text(cue["text"], len(cue["text"]), cue["duration"])
    if len(parts) <= 1:
        return [cue]
    total_len = sum(len(p) for p in parts) or 1
    out = []
    offset = 0.0
    for p in parts:
        part_duration = cue["duration"] * (len(p) / total_len)
        out.append({"text": p, "start": cue["start"] + offset, "duration": part_duration})
        offset += part_duration
    return out


def _merge_into_sentences(cues: list[dict]) -> list[CaptionSentence]:
    """
    Merge consecutive cues into sentence-level chunks with start/end
    timestamps. A manually-authored cue almost always already ends in
    punctuation, so this is effectively a 1:1 pass-through for those —
    the merging logic only does real work on unpunctuated ASR streams.
    """
    cues = [sub for cue in cues for sub in _split_cue_into_sentences(cue)]
    out: list[CaptionSentence] = []
    buf_text: list[str] = []
    buf_start: float | None = None
    buf_end = 0.0
    # Tracks the furthest cue-end seen so far, independent of buf_end
    # (which resets on every flush) — needed to detect a cue jumping
    # backward in time even right after a fresh buffer started.
    last_cue_end = 0.0

    def flush() -> None:
        if buf_text and buf_start is not None:
            out.append(CaptionSentence(start=buf_start, end=buf_end, text="".join(buf_text)))

    for cue in cues[:_MAX_CUES]:
        text = cue["text"].strip().replace("\n", " ")
        if not text:
            continue
        # Tracks should be chronological, but broken ones carry cues that
        # jump backward; those would give a sentence with end < start.
        # Drop anything that isn't roughly forward-moving rather than
        # guessing how to reorder broken data.
        if cue["start"] < last_cue_end - 0.5:
            continue
        last_cue_end = max(last_cue_end, cue["start"] + cue["duration"])
        # Check both caps before appending, so a block never overshoots a
        # cap by up to one whole cue.
        prospective_len = sum(len(t) for t in buf_text) + len(text)
        prospective_end = cue["start"] + cue["duration"]
        too_long = buf_text and prospective_len > _MAX_SENTENCE_CHARS
        too_slow = buf_start is not None and (prospective_end - buf_start) > _MAX_SENTENCE_SECONDS
        if buf_text and (too_long or too_slow):
            flush()
            buf_text = []
            buf_start = None
        if buf_start is None:
            buf_start = cue["start"]
        buf_text.append(text)
        buf_end = cue["start"] + cue["duration"]
        if any(p in text for p in _SENTENCE_END):
            flush()
            buf_text = []
            buf_start = None

    flush()
    return out


def fetch_captioned_sentences(video_id: str) -> tuple[list[CaptionSentence], bool]:
    """
    Fetch + sentence-merge the best Chinese caption track for a video.

    Returns (sentences, is_generated) — is_generated flags ASR captions so
    the caller can warn the user that segmentation/accuracy may be rougher
    than a manually-authored track.
    """
    cues, is_generated = _fetch_raw_cues(video_id)
    sentences = _merge_into_sentences(cues)
    if not sentences:
        raise YoutubeCaptionError("The caption track came back empty.")
    return sentences, is_generated
