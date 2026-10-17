import logging
import os
import re

import httpx
from cachetools import TTLCache

from app.core.constants import (
    API_TIMEOUT,
    TRANSLATION_CACHE_SIZE,
    TRANSLATION_CACHE_TTL,
    TRANSLATION_SOURCE_DEEPL,
    TRANSLATION_SOURCE_GOOGLE,
    TRANSLATION_SOURCE_LLM,
    TRANSLATION_SOURCE_MYMEMORY,
)
from app.services import llm

logger = logging.getLogger(__name__)

translation_cache: TTLCache = TTLCache(maxsize=TRANSLATION_CACHE_SIZE, ttl=TRANSLATION_CACHE_TTL)


async def _call_translation_api(
    client: httpx.AsyncClient, url: str, method: str = "POST", **kwargs
) -> httpx.Response:
    if method.upper() == "POST":
        response = await client.post(url, **kwargs)
    else:
        response = await client.get(url, **kwargs)
    response.raise_for_status()
    return response


LLM_FEATURE = "translate"
# Longer texts go to the translation APIs: an LLM answer would take long.
LLM_MAX_CHARS = 1500
LLM_TIMEOUT = 25
_CJK = re.compile(r"[\u3400-\u9fff]")

LLM_PROMPT = """Translate this Chinese text into natural, faithful English that stays close to the
Chinese, for a learner reading the original. Reply with the translation only.
{terms}
Text: {text}"""


async def _llm_translation(text: str, terms: list[tuple[str, str]]) -> dict | None:
    """The server's LLM, first when it is up: as good as DeepL on everyday
    text, and it can use the text's glossary for a school's terms."""
    if len(text) > LLM_MAX_CHARS or not llm.enabled(LLM_FEATURE):
        return None
    listed = (
        "Use these renderings for terms when they carry that meaning:\n"
        + "\n".join(f"- {zh} = {en}" for zh, en in terms)
        + "\n"
        if terms
        else ""
    )
    try:
        reply = await llm.chat(
            [{"role": "user", "content": LLM_PROMPT.format(terms=listed, text=text)}],
            max_tokens=min(4000, 200 + 4 * len(text)),
            temperature=0.2,
            timeout=LLM_TIMEOUT,
        )
    except llm.LlmError as e:
        logger.warning("LLM translation failed: %s", e)
        return None
    out = str(reply or "").strip().strip('"').strip()
    # An answer in Chinese (or empty) is no translation.
    if not out or len(_CJK.findall(out)) > len(out) / 3:
        return None
    return {"translation": out, "source": TRANSLATION_SOURCE_LLM}


async def get_translation_with_source(
    text: str, terms: list[tuple[str, str]] | None = None
) -> dict | None:
    """
    Get translation with multiple API support and source tracking.
    Priority: the server's LLM (with the glossary `terms` in the text) >
    DeepL > Google > MyMemory.
    """
    result = await _llm_translation(text, terms or [])
    if result:
        return result

    deepl_key = os.getenv("DEEPL_API_KEY")
    google_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")

    # DeepL — header auth required since Nov 2025.
    if deepl_key:
        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                url = "https://api-free.deepl.com/v2/translate"
                headers = {"Authorization": f"DeepL-Auth-Key {deepl_key}"}
                data = {"text": text, "target_lang": "EN", "source_lang": "ZH"}
                response = await _call_translation_api(
                    client, url, method="POST", headers=headers, data=data
                )
                result = response.json()
                if result.get("translations"):
                    return {
                        "translation": result["translations"][0]["text"],
                        "source": TRANSLATION_SOURCE_DEEPL,
                    }
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300] if e.response is not None else ""
            logger.error(f"DeepL API error {e.response.status_code} for '{text}': {body}")
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(f"DeepL API network error for '{text}': {e}")
        except Exception as e:
            logger.error(f"DeepL API failed for '{text}': {e}", exc_info=True)

    if google_key:
        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                url = "https://translation.googleapis.com/language/translate/v2"
                params = {"key": google_key, "q": text, "target": "en", "source": "zh"}
                response = await _call_translation_api(client, url, method="POST", params=params)
                result = response.json()
                if result.get("data", {}).get("translations"):
                    return {
                        "translation": result["data"]["translations"][0]["translatedText"],
                        "source": TRANSLATION_SOURCE_GOOGLE,
                    }
        except httpx.HTTPStatusError as e:
            logger.warning(f"Google Translate API error {e.response.status_code} for '{text}'")
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(f"Google Translate API network error for '{text}': {e}")
        except Exception as e:
            logger.debug(f"Google Translate API failed for '{text}': {e}")

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            url = f"https://api.mymemory.translated.net/get?q={text}&langpair=zh|en"
            response = await _call_translation_api(client, url, method="GET")
            result = response.json()
            if result.get("responseStatus") == 200:
                return {
                    "translation": result["responseData"]["translatedText"],
                    "source": TRANSLATION_SOURCE_MYMEMORY,
                }
    except httpx.HTTPStatusError as e:
        logger.warning(f"MyMemory API error {e.response.status_code} for '{text}'")
    except (httpx.TimeoutException, httpx.NetworkError) as e:
        logger.warning(f"MyMemory API network error for '{text}': {e}")
    except Exception as e:
        logger.debug(f"MyMemory API failed for '{text}': {e}")

    return None
