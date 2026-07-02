"""
POST /api/pronounce — server-side pronunciation assessment.

Accepts:
- `audio`: WebM / Ogg / WAV / MP3 file uploaded as multipart/form-data.
- `word`: the hanzi the user was asked to pronounce (form field).
- `pinyin`: optional comma-separated tone-marked pinyin per character.
  Falls back to pypinyin on the server when omitted.

Returns a JSON shape `score_pronunciation` produces — per-syllable
character match + tone score + overall.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.auth import require_auth
from app.database import User
from app.services.pronounce import score_pronunciation
from app.services.script import to_canonical

router = APIRouter(tags=["Pronounce"])

# Cap to keep RAM bounded — a 30-second 16 kHz mono PCM clip is ~1 MB;
# we'd be very surprised by a 5 MB pronunciation card.
_MAX_AUDIO_BYTES = 5 * 1024 * 1024


@router.post("/api/pronounce")
async def pronounce(
    audio: UploadFile = File(...),
    word: str = Form(...),
    pinyin: str = Form(""),
    user: User = Depends(require_auth),
) -> dict:
    audio_bytes = await audio.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="audio is empty")
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio too large (5 MB cap)")
    if not word.strip():
        raise HTTPException(status_code=400, detail="word is required")

    # Normalise the target to Simplified so the Whisper transcript (which
    # comes back in simp regardless of how we asked) lines up with our
    # per-character comparison.
    word_simp = to_canonical(word.strip(), user)
    expected_pinyins = [p.strip() for p in pinyin.split(",") if p.strip()]

    try:
        # Whisper inference + librosa pitch extraction take seconds of CPU;
        # run in the threadpool so they don't freeze the event loop (one of
        # only two uvicorn workers) for every other request in flight.
        result = await run_in_threadpool(
            score_pronunciation, audio_bytes, word_simp, expected_pinyins
        )
    except Exception as e:  # noqa: BLE001 — decode/transcription failures shouldn't 500
        raise HTTPException(
            status_code=500, detail=f"Couldn't process audio: {type(e).__name__}: {e}"
        ) from e

    return {
        "transcript": result.transcript,
        "overall_score": result.overall_score,
        "syllables": [asdict(s) for s in result.syllables],
        "notes": result.notes,
    }
