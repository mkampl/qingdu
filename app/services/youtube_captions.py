"""
YouTube caption fetch + sentence-merge for the watch-and-read prototype.

Pulls a Chinese caption track for a public YouTube video via the same
public `timedtext` endpoint the YouTube player itself calls to render
captions in-browser — no API key. (The official Data API v3
`captions.download` endpoint requires OAuth *as the video's own channel
owner*, which is structurally useless for pulling captions off an
arbitrary third-party video — see the youtube-transcript-api README.)

Manually-authored caption tracks are already real, punctuated sentences
and need no further work. Auto-generated (ASR) Chinese tracks are almost
always one long unpunctuated word stream, so those get re-segmented here
by merging consecutive cues until we hit sentence-ending punctuation or a
length cap.

Known risk (documented upstream, not paranoia): YouTube has been blocking
some requests from cloud/datacenter IP ranges. Empirically this VPS was
NOT blocked as of 2026-09-02 — but callers should cache aggressively
(a video's captions never change) so a block, if it ever happens, costs
one failed fetch instead of breaking every subsequent view.
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

# Real terminal punctuation always closes a sentence. Commas/enumeration
# commas are a *soft* close — added after real-world captions turned out
# to rarely carry a full stop mid-narration, which let unrelated clauses
# glue into one multi-second highlighted block (a 73-char, 14s block was
# observed on a real TED zh-Hans track). A cue containing a comma still
# closes cleanly on a complete clause, since we only ever cut at cue
# boundaries, never mid-cue.
_SENTENCE_END = "。！？!?…，、"
_MAX_SENTENCE_CHARS = 25
# A caption track can carry zero punctuation of any kind (observed: a
# fansubbed episode, "manually created" track, no full stops and no
# commas anywhere) and can have long silent/no-dialogue gaps between
# cues. The char cap alone doesn't catch that second case — a
# 168-second block was observed spanning a scene change, since only
# ~68 characters were spoken across that whole span. This time cap
# forces a cut regardless of character count once a block runs long.
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


def _split_cue_into_sentences(cue: dict) -> list[dict]:
    """
    Split one cue's own text at real sentence-ending punctuation into
    sub-cues, distributing its [start, end] span proportionally by
    character count. A cue with no internal sentence break comes back
    unchanged.

    Needed for Whisper/SRT-sourced cues specifically (see qingdu-watch,
    the companion tool this module was ported to): ASR timestamps only
    exist at the segment level, and a segment routinely bundles several
    complete sentences into one multi-second block — the highlight then
    lagged 4-5 real sentences behind the audio. There's no true
    per-sentence timing to fall back on, so this is a proportional-by-
    length approximation, not exact — but a large improvement over one
    highlight per ASR segment. Harmless no-op for ordinary YouTube
    caption cues, which are usually already single clauses.
    """
    parts = [p for p in _SENTENCE_BOUNDARY.split(cue["text"]) if p.strip()]
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
        # Real caption tracks are supposed to be chronological, but a
        # fansubbed episode was observed with a chunk of duplicate/corrupt
        # cues jumping backward by hundreds of seconds partway through —
        # trusting that blindly produced a sentence with end < start.
        # Silently drop anything that isn't roughly forward-moving rather
        # than trying to guess how to reorder genuinely broken data.
        if cue["start"] < last_cue_end - 0.5:
            continue
        last_cue_end = max(last_cue_end, cue["start"] + cue["duration"])
        # Check both caps *before* appending — checking after let a block
        # overshoot by up to one whole cue's length (a 31-char result was
        # observed with a 25-char cap), since by then it's too late to
        # avoid adding this cue to the block that's about to close anyway.
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
