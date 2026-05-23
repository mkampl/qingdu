"""Text-to-speech via Google Translate's public TTS endpoint."""

import asyncio
import re
from urllib.parse import quote

import httpx

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_TTS_URL = "https://translate.google.com/translate_tts"
_TIMEOUT_SECONDS = 10.0

# Google's public TTS endpoint hard-caps the `q` param around 200 chars; we
# leave a small margin so URL-encoding doesn't push us over. Sentences
# longer than this get split at punctuation boundaries and the resulting
# MP3s are byte-concatenated — most decoders handle that fine because each
# MP3 frame is self-describing.
_MAX_CHARS_PER_REQUEST = 180
_SPLIT_PUNCTUATION = re.compile(r"([,，。！？；：、,.!?;:])")


async def fetch_chinese_tts(text: str) -> bytes:
    """
    Fetch MP3 audio bytes for a Chinese phrase. Handles long inputs by
    splitting on punctuation and concatenating the resulting MP3 streams.
    Raises httpx.HTTPError on failure.
    """
    text = text.strip()
    if not text:
        return b""
    chunks = _split_for_tts(text)
    if len(chunks) == 1:
        return await _fetch_single(chunks[0])
    # Fetch chunks in parallel (modest concurrency — these go to the same
    # Google endpoint and we don't want to look bot-like).
    results = await asyncio.gather(*(_fetch_single(c) for c in chunks))
    return b"".join(results)


async def _fetch_single(text: str) -> bytes:
    url = f"{_TTS_URL}?ie=UTF-8&q={quote(text)}&tl=zh-CN&client=gtx"
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        return response.content


def _split_for_tts(text: str) -> list[str]:
    """
    Split `text` into pieces no longer than _MAX_CHARS_PER_REQUEST. Prefer
    punctuation boundaries; fall back to hard slicing when a single run of
    characters exceeds the limit (rare for natural Chinese prose).
    """
    if len(text) <= _MAX_CHARS_PER_REQUEST:
        return [text]

    # First pass: split on punctuation, keeping the punctuation glued to the
    # preceding piece so the audio retains its natural pause.
    parts = _SPLIT_PUNCTUATION.split(text)
    rejoined: list[str] = []
    buf = ""
    for piece in parts:
        if not piece:
            continue
        buf += piece
        if _SPLIT_PUNCTUATION.fullmatch(piece):
            # `piece` is a punctuation match — close the chunk after it.
            rejoined.append(buf)
            buf = ""
    if buf:
        rejoined.append(buf)

    # Second pass: pack pieces back into chunks no larger than the limit.
    chunks: list[str] = []
    current = ""
    for piece in rejoined:
        # If the piece alone is already too long, hard-slice it.
        while len(piece) > _MAX_CHARS_PER_REQUEST:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(piece[:_MAX_CHARS_PER_REQUEST])
            piece = piece[_MAX_CHARS_PER_REQUEST:]
        if len(current) + len(piece) > _MAX_CHARS_PER_REQUEST:
            chunks.append(current)
            current = piece
        else:
            current += piece
    if current:
        chunks.append(current)
    return chunks
