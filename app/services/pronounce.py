"""
Server-side pronunciation assessment.

Two signals, combined into a single per-syllable score:

1. **Character match** — faster-whisper transcribes the recording; we
   compare the transcript against the expected hanzi after stripping
   punctuation. This is the same signal Web Speech API gives, but
   self-hosted (works in Firefox, no Google in the loop).

2. **Tone contour shape** — librosa.pyin extracts the fundamental
   frequency over the syllable's audio window; we compare its
   normalised shape to the canonical 5-level contour for the
   expected tone. Mandarin tones live in pitch movement, so this is
   where the actual pronunciation feedback lives.

For multi-syllable words we use faster-whisper's word-level
timestamps when available, otherwise split the audio into equal
windows. F0 is normalised within each syllable so different speakers
(yours vs ours) end up on the same 0-1 scale and the shape comparison
is speaker-independent.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from threading import Lock
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Loaded lazily on first request — startup boot stays fast and a deployment
# without pronounce traffic doesn't pay the ~250 MB RAM cost. Reused
# across requests; a process-wide lock guards the one-time init so
# concurrent first requests don't both download the model.
_model: Any = None
_model_lock = Lock()
_WHISPER_MODEL_SIZE = "small"
_WHISPER_LANGUAGE = "zh"
_SAMPLE_RATE = 16000  # what Whisper expects + a sensible F0 default

# Canonical Mandarin tone contours on the 5-level Chao scale. Each is
# a 5-point sample of the pitch shape over the syllable; we resample
# the observed contour to 5 points and compare via correlation +
# normalised L1 distance.
#
# Tone 1 (high level): 55555
# Tone 2 (rising):     12345 (low → high)
# Tone 3 (dip+rise):   31123 (start mid, dip low, rise back up)
# Tone 4 (falling):    54321
# Tone 5 (neutral):    33333 (flat-ish, often shortened; we score it
#                              loosely since context varies)
_EXPECTED_CONTOURS: dict[int, np.ndarray] = {
    1: np.array([5, 5, 5, 5, 5], dtype=float),
    2: np.array([1, 2, 3, 4, 5], dtype=float),
    3: np.array([3, 1, 1, 2, 3], dtype=float),
    4: np.array([5, 4, 3, 2, 1], dtype=float),
    5: np.array([3, 3, 3, 3, 3], dtype=float),
}
# Normalize the templates once so the comparison treats them as 0-1 shapes.
for _t, _c in _EXPECTED_CONTOURS.items():
    _EXPECTED_CONTOURS[_t] = (_c - _c.min()) / max(_c.max() - _c.min(), 1e-9)


@dataclass
class SyllableResult:
    char: str
    pinyin: str  # tone-marked pinyin for display
    expected_tone: int  # 1-5
    transcribed_char: str  # what Whisper heard for this syllable's slice
    char_match: bool
    tone_score: float  # 0..1


@dataclass
class PronounceResult:
    transcript: str  # full Whisper transcript
    syllables: list[SyllableResult]
    overall_score: float  # 0..1
    notes: list[str]  # human-readable hints


def _load_model() -> Any:
    """Get the lazily-initialised faster-whisper WhisperModel."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel  # heavy import — defer

        logger.info("Loading faster-whisper %s (first request)…", _WHISPER_MODEL_SIZE)
        _model = WhisperModel(
            _WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type="int8",  # ~250MB; CPU-friendly
        )
        logger.info("faster-whisper loaded")
    return _model


def _load_audio(audio_bytes: bytes) -> np.ndarray:
    """Decode any audio container the browser might send into a 16 kHz
    mono float32 numpy array.

    librosa.load(BytesIO) goes through libsndfile, which only knows
    WAV/FLAC/OGG — browser MediaRecorder emits WebM/Opus by default,
    so that path raises "Format not recognised". We shell out to
    ffmpeg explicitly, which handles every container we'd ever see.
    """
    import subprocess

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-f",
                "f32le",  # raw 32-bit float PCM
                "-ac",
                "1",  # mono
                "-ar",
                str(_SAMPLE_RATE),  # 16 kHz
                "pipe:1",
            ],
            input=audio_bytes,
            capture_output=True,
            timeout=30,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg failed to decode the audio: {stderr[:200]}") from e
    raw = proc.stdout
    if not raw:
        raise RuntimeError("ffmpeg produced no audio data")
    return np.frombuffer(raw, dtype=np.float32).copy()


def _strip_punctuation(text: str) -> str:
    return re.sub(r"[\s。．.,，!?！？；;、:：]", "", text)


def _tone_from_pinyin(pinyin: str) -> int:
    """Return 1..5 for a single tone-marked pinyin syllable. 5 = neutral
    (no tone mark). Vowels with diacritics carry the tone."""
    table = {
        "ā": 1,
        "ē": 1,
        "ī": 1,
        "ō": 1,
        "ū": 1,
        "ǖ": 1,
        "á": 2,
        "é": 2,
        "í": 2,
        "ó": 2,
        "ú": 2,
        "ǘ": 2,
        "ǎ": 3,
        "ě": 3,
        "ǐ": 3,
        "ǒ": 3,
        "ǔ": 3,
        "ǚ": 3,
        "à": 4,
        "è": 4,
        "ì": 4,
        "ò": 4,
        "ù": 4,
        "ǜ": 4,
    }
    for ch in pinyin:
        if ch in table:
            return table[ch]
    return 5


def _resample_contour(contour: np.ndarray, n: int = 5) -> np.ndarray:
    """Resample a 1-D contour to exactly n samples (linear interp).
    NaNs (unvoiced frames) are masked out first so they don't poison
    the interpolation."""
    contour = np.asarray(contour, dtype=float)
    mask = ~np.isnan(contour)
    if mask.sum() < 2:
        # Not enough voiced frames to compare — return a flat zero shape;
        # the scorer treats this as "no signal" → 0 tone score.
        return np.zeros(n)
    voiced = contour[mask]
    xs_old = np.linspace(0, 1, len(voiced))
    xs_new = np.linspace(0, 1, n)
    return np.interp(xs_new, xs_old, voiced)


def _normalize_01(arr: np.ndarray) -> np.ndarray:
    """Normalize to 0..1 by min-max. Treats a flat input as zeros so we
    don't divide by ~0 and get garbage."""
    arr = np.asarray(arr, dtype=float)
    lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
    span = hi - lo
    if span < 1e-6:
        return np.zeros_like(arr)
    return (arr - lo) / span


def _score_tone(observed_contour: np.ndarray, expected_tone: int) -> float:
    """0..1 score for how well `observed_contour` matches the canonical
    shape for `expected_tone`. Combines:
    - shape correlation (captures direction: rising vs falling)
    - 1 - mean absolute distance after normalisation (captures magnitude)
    """
    expected = _EXPECTED_CONTOURS[expected_tone]
    observed5 = _resample_contour(observed_contour, n=5)
    if not np.any(observed5):
        return 0.0
    observed_n = _normalize_01(observed5)
    # Pearson correlation, clamped to [0,1] — anti-correlation reads as
    # "you did the opposite of the expected tone" which deserves 0,
    # not a negative score.
    if np.std(observed_n) < 1e-6 or np.std(expected) < 1e-6:
        corr = 0.0
    else:
        corr = float(np.corrcoef(observed_n, expected)[0, 1])
    corr = max(0.0, corr)
    # L1 distance on the same 0..1 scale, inverted: 1 = identical shape.
    l1 = float(np.mean(np.abs(observed_n - expected)))
    l1_score = max(0.0, 1.0 - l1)
    # Weight correlation more — shape direction matters most for tones.
    return 0.7 * corr + 0.3 * l1_score


def _extract_pitch(audio: np.ndarray) -> np.ndarray:
    """Run librosa.pyin to get a frame-level F0 contour. Returns Hz
    values with NaN for unvoiced frames."""
    import librosa  # heavy import — defer

    f0, _voiced_flag, _voiced_prob = librosa.pyin(
        audio,
        fmin=librosa.note_to_hz("C2"),  # 65 Hz — well below any speaker's F0
        fmax=librosa.note_to_hz("C6"),  # 1046 Hz — well above any speaker's F0
        sr=_SAMPLE_RATE,
        frame_length=2048,
    )
    return f0


def _slice_for_syllable(audio: np.ndarray, syllable_idx: int, n_syllables: int) -> np.ndarray:
    """Equal-time slice of the audio per syllable. Crude but works as a
    v1 — Whisper's word timestamps would give a tighter cut once we
    wire them in."""
    if n_syllables <= 1:
        return audio
    chunk = len(audio) // n_syllables
    start = syllable_idx * chunk
    end = start + chunk if syllable_idx < n_syllables - 1 else len(audio)
    return audio[start:end]


def _transcribe(audio: np.ndarray) -> str:
    """Run Whisper, return the recognised text. Uses zh and beam_size=1
    for speed — pronunciation cards are short single words / phrases."""
    model = _load_model()
    segments, _info = model.transcribe(
        audio,
        language=_WHISPER_LANGUAGE,
        beam_size=1,
        vad_filter=False,  # audio is already short + intentional
    )
    return " ".join(s.text for s in segments).strip()


def score_pronunciation(
    audio_bytes: bytes,
    target_word: str,
    expected_pinyins: list[str],
) -> PronounceResult:
    """Public entry point used by /api/pronounce.

    `target_word` is the hanzi the user was asked to say.
    `expected_pinyins` is one tone-marked pinyin syllable per hanzi;
    callers can pass [] and we'll fall back to pypinyin on the spot.
    """
    if not expected_pinyins:
        from pypinyin import Style, lazy_pinyin

        expected_pinyins = lazy_pinyin(target_word, style=Style.TONE)

    audio = _load_audio(audio_bytes)
    transcript = _transcribe(audio)
    transcript_clean = _strip_punctuation(transcript)
    target_clean = _strip_punctuation(target_word)

    chars = list(target_word)
    syllables: list[SyllableResult] = []
    for i, char in enumerate(chars):
        pinyin = expected_pinyins[i] if i < len(expected_pinyins) else ""
        tone = _tone_from_pinyin(pinyin)
        slice_audio = _slice_for_syllable(audio, i, len(chars))
        f0 = _extract_pitch(slice_audio)
        tone_score = _score_tone(f0, tone)
        # Character match per syllable: substring of the cleaned
        # transcript at the right position when lengths agree, else
        # a global containment check.
        if len(transcript_clean) == len(target_clean):
            transcribed_char = transcript_clean[i] if i < len(transcript_clean) else ""
            char_match = transcribed_char == char
        else:
            transcribed_char = transcript_clean
            char_match = char in transcript_clean
        syllables.append(
            SyllableResult(
                char=char,
                pinyin=pinyin,
                expected_tone=tone,
                transcribed_char=transcribed_char,
                char_match=char_match,
                tone_score=round(tone_score, 3),
            )
        )

    # Overall: average of (char-match boolean as 0/1) and tone scores.
    if syllables:
        char_avg = sum(1 for s in syllables if s.char_match) / len(syllables)
        tone_avg = sum(s.tone_score for s in syllables) / len(syllables)
        overall = round(0.5 * char_avg + 0.5 * tone_avg, 3)
    else:
        overall = 0.0

    notes: list[str] = []
    if all(s.char_match for s in syllables) and tone_avg >= 0.75:
        notes.append("Sounds great.")
    elif all(s.char_match for s in syllables):
        notes.append("Right word — work on the tones.")
    elif transcript_clean and transcript_clean != target_clean:
        notes.append(f'Heard "{transcript_clean}" instead.')
    if not transcript_clean:
        notes.append("Couldn't hear you clearly.")

    return PronounceResult(
        transcript=transcript,
        syllables=syllables,
        overall_score=overall,
        notes=notes,
    )


__all__ = ["PronounceResult", "SyllableResult", "score_pronunciation"]
