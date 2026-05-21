"""Text-to-speech via Google Translate's public TTS endpoint."""

from urllib.parse import quote

import httpx

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_TTS_URL = "https://translate.google.com/translate_tts"
_TIMEOUT_SECONDS = 10.0


async def fetch_chinese_tts(text: str) -> bytes:
    """Fetch MP3 audio bytes for a Chinese phrase. Raises httpx.HTTPError on failure."""
    url = f"{_TTS_URL}?ie=UTF-8&q={quote(text)}&tl=zh-CN&client=gtx"
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.get(url, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        return response.content
