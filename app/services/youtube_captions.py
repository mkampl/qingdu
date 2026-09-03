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

_SENTENCE_END = "。！？!?…"
_MAX_SENTENCE_CHARS = 60  # ASR cues rarely carry punctuation; caps run-on merges
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


def _merge_into_sentences(cues: list[dict]) -> list[CaptionSentence]:
    """
    Merge consecutive cues into sentence-level chunks with start/end
    timestamps. A manually-authored cue almost always already ends in
    punctuation, so this is effectively a 1:1 pass-through for those —
    the merging logic only does real work on unpunctuated ASR streams.
    """
    out: list[CaptionSentence] = []
    buf_text: list[str] = []
    buf_start: float | None = None
    buf_end = 0.0

    def flush() -> None:
        if buf_text and buf_start is not None:
            out.append(CaptionSentence(start=buf_start, end=buf_end, text="".join(buf_text)))

    for cue in cues[:_MAX_CUES]:
        text = cue["text"].strip().replace("\n", " ")
        if not text:
            continue
        if buf_start is None:
            buf_start = cue["start"]
        buf_text.append(text)
        buf_end = cue["start"] + cue["duration"]
        joined_len = sum(len(t) for t in buf_text)
        if any(p in text for p in _SENTENCE_END) or joined_len >= _MAX_SENTENCE_CHARS:
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
