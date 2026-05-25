"""
CC-CEDICT loader.

Pulls the canonical Chinese-English dictionary file from mdbg.net's
weekly export, parses each entry and populates `app.state.cedict_vocab`
keyed by simplified form. Then merges the better meanings into the
already-loaded `hsk_vocab` so every downstream consumer (analyze,
review queue, word_info snapshots) sees the richer glosses without
further code changes.

CC-CEDICT format (one entry per line, # comments at file top):
    傳統 传统 [chuan2 tong3] /tradition/convention/heritage/CL:個|个[ge4]/

We:
- drop the bare-CL classifier annotations from `meanings` (they're not
  glosses, they're grammatical metadata),
- convert tone-numbered pinyin (chuan2 tong3) to tone-marked
  (chuán tǒng) so it lines up with the rest of the app,
- write the unzipped file to `data/cedict_ts.u8` so subsequent restarts
  skip the download.

License of CC-CEDICT data: CC-BY-SA 4.0.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.constants import (
    CEDICT_REFRESH_DAYS,
    CEDICT_SOURCE_TAG,
    CEDICT_URL,
    HSK_DOWNLOAD_TIMEOUT,
    HSK_RETRY_MAX_WAIT,
    HSK_RETRY_MIN_WAIT,
    MAX_RETRY_ATTEMPTS,
)
from app.core.paths import DATA_DIR
from app.state import cedict_vocab, hsk_vocab

logger = logging.getLogger(__name__)

CEDICT_CACHE_FILE: Path = DATA_DIR / "cedict_ts.u8"

# Lines starting with # are header/comments; we skip them.
_ENTRY_RE = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.+?)/\s*$")
# CL:個|个[ge4] — classifier annotations. We strip these from meanings since
# they describe grammar, not sense.
_CL_RE = re.compile(r"^CL:")


# --- tone-number → tone-mark conversion ----------------------------------------
#
# CC-CEDICT pinyin uses tone-number form ("chuan2"). The rest of the app
# expects tone-mark form ("chuán"). Mark placement follows the standard
# rule: a > e > o (when no a/e/o, the last vowel takes the mark).
_TONE_MARKS = {
    "a": "āáǎà",
    "e": "ēéěè",
    "i": "īíǐì",
    "o": "ōóǒò",
    "u": "ūúǔù",
    "ü": "ǖǘǚǜ",
}
# Order of preference for where the tone mark sits in a syllable.
_VOWEL_PRIORITY = ["a", "e", "o", "ou", "u", "i", "ü"]


def _apply_tone(syllable: str) -> str:
    """Turn one numbered syllable (e.g. 'chuan2') into 'chuán'."""
    if not syllable:
        return ""
    if syllable[-1].isdigit():
        tone = int(syllable[-1])
        body = syllable[:-1]
    else:
        return syllable
    if tone < 1 or tone > 4:
        # Tone 5 (neutral) gets no mark; tone 0 / any other gets no mark.
        return body
    body = body.replace("u:", "ü").replace("v", "ü")
    # Find the vowel that takes the mark, in priority order.
    target_index = -1
    for vowel in _VOWEL_PRIORITY:
        idx = body.find(vowel)
        if idx >= 0:
            # For "ou", the o gets the mark — that's already idx of "o".
            target_index = idx
            break
    if target_index < 0:
        return body
    target_char = body[target_index]
    marked = _TONE_MARKS.get(target_char, target_char * 4)[tone - 1]
    return body[:target_index] + marked + body[target_index + 1 :]


def _convert_pinyin(numbered: str) -> str:
    """Convert space-separated numbered pinyin to space-separated tone-marked."""
    syllables = numbered.strip().split()
    return " ".join(_apply_tone(s.lower()) for s in syllables)


# --- file fetch + parse --------------------------------------------------------


def _is_cache_fresh() -> bool:
    """True if cedict_ts.u8 exists and is younger than CEDICT_REFRESH_DAYS."""
    if not CEDICT_CACHE_FILE.exists():
        return False
    mtime = datetime.fromtimestamp(CEDICT_CACHE_FILE.stat().st_mtime)
    return datetime.now() - mtime < timedelta(days=CEDICT_REFRESH_DAYS)


@retry(
    stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=HSK_RETRY_MIN_WAIT, max=HSK_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.RequestError)),
    reraise=True,
)
async def _download_zip() -> bytes:
    async with httpx.AsyncClient(timeout=HSK_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        r = await client.get(CEDICT_URL)
        r.raise_for_status()
        return r.content


def _extract_u8(zip_bytes: bytes) -> str:
    """Extract the single .u8 file out of the CC-CEDICT zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = [n for n in z.namelist() if n.endswith(".u8")]
        if not names:
            raise RuntimeError("cedict zip did not contain a .u8 file")
        return z.read(names[0]).decode("utf-8")


def _looks_minor(primary: str) -> bool:
    """Surname or variant-of placeholder entries — almost never what a
    learner is looking up first."""
    return primary.startswith("surname ") or primary.startswith("variant of ")


def _looks_grammatical_only(primary: str) -> bool:
    """Entries whose primary gloss is a function-word marker (particles,
    auxiliaries, interjections) rather than a content definition. For
    polysemous characters like 地 / 了 / 着 / 过 / 子 / 的 these are the
    'wrong' reading to surface as the headline meaning for a learner —
    they'd encounter the content reading (earth, finish, wear, cross,
    child, possessive) far more often."""
    m = primary.lower().strip()
    if m.startswith("-"):
        # CC-CEDICT writes adverbial-particle 地 as "-ly", possessive 的 as "of/-ly/etc".
        return True
    return (
        "particle" in m
        or m.startswith("(used ")
        or m.startswith("auxiliary")
        or m.startswith("modal ")
        or m.startswith("interjection")
        or m.startswith("exclamation")
        or m.startswith("(literary")
        or m.startswith("(coll.")
        or m.startswith("(of ")
    )


def _is_all_neutral_tone(numbered_pinyin: str) -> bool:
    """True when every syllable in the reading carries CC-CEDICT's
    neutral-tone marker (digit 5). Neutral-tone-only readings in CC-CEDICT
    overwhelmingly mark grammatical particles (de, le, zhe, ne) rather
    than content words."""
    syllables = numbered_pinyin.strip().split()
    if not syllables:
        return False
    return all(s.endswith("5") for s in syllables)


def _entry_quality(primary: str, numbered_pinyin: str) -> int:
    """Higher = better headline candidate. Used to resolve collisions
    when CC-CEDICT lists multiple readings of the same simplified form."""
    score = 100
    if _looks_minor(primary):
        score -= 100
    if _looks_grammatical_only(primary):
        score -= 50
    if _is_all_neutral_tone(numbered_pinyin):
        # On its own neutral tone is suggestive, not damning — only
        # penalise so it loses to a content reading but still beats a
        # surname-only entry of the same character.
        score -= 30
    return score


def _parse_text(text: str) -> dict[str, dict]:
    """Parse a CC-CEDICT .u8 text into {simplified: entry} dict.

    On collisions (multiple pinyin readings of the same simplified form),
    `_entry_quality` picks the more useful headline reading: content
    words beat particle-only readings, full-tone pinyin beats all-neutral,
    and surname / variant-of placeholders lose to anything else.
    """
    out: dict[str, dict] = {}
    # Track which existing entry's quality we'd be comparing against
    # without recomputing on each pass.
    quality_cache: dict[str, int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _ENTRY_RE.match(line)
        if not m:
            continue
        traditional = m.group(1)
        simplified = m.group(2)
        numbered_pinyin = m.group(3)
        glosses_raw = m.group(4)
        meanings = [g for g in glosses_raw.split("/") if g and not _CL_RE.match(g)]
        if not meanings:
            continue
        primary = meanings[0]
        new_quality = _entry_quality(primary, numbered_pinyin)
        existing_quality = quality_cache.get(simplified)
        if existing_quality is not None and new_quality <= existing_quality:
            continue
        out[simplified] = {
            "traditional": traditional,
            "pinyin": _convert_pinyin(numbered_pinyin),
            "meaning": primary,
            "meanings": meanings,
            "source": CEDICT_SOURCE_TAG,
        }
        quality_cache[simplified] = new_quality
    return out


def _merge_into_hsk_vocab() -> tuple[int, int]:
    """For every HSK word also in CC-CEDICT, overlay the richer meanings.

    Returns (overlaid_count, missing_count) for logging.
    """
    overlaid = 0
    missing = 0
    for word, hsk_entry in hsk_vocab.items():
        cedict_entry = cedict_vocab.get(word)
        if not cedict_entry:
            missing += 1
            continue
        hsk_entry["meaning"] = cedict_entry["meaning"]
        hsk_entry["meanings"] = cedict_entry["meanings"]
        # Leave pinyin alone — the HSK source already carries good
        # tone-marked pinyin and matches the rest of the app's data.
        overlaid += 1
    return overlaid, missing


# --- public entry point --------------------------------------------------------


async def load_cedict(force_refresh: bool = False) -> None:
    """Populate `cedict_vocab` + merge meanings into `hsk_vocab`.

    Safe to call even if the network is down — we fall back to the cached
    file. If both fail (no cache + no network), CC-CEDICT is just absent
    and the app keeps working on the existing HSK data.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    text: str | None = None

    if force_refresh or not _is_cache_fresh():
        try:
            logger.info("Downloading CC-CEDICT from %s", CEDICT_URL)
            zip_bytes = await _download_zip()
            text = _extract_u8(zip_bytes)
            CEDICT_CACHE_FILE.write_text(text, encoding="utf-8")
            logger.info("CC-CEDICT cache refreshed: %s", CEDICT_CACHE_FILE)
        except Exception as e:
            logger.warning("CC-CEDICT download failed (%s); will use cached copy if any", e)

    if text is None and CEDICT_CACHE_FILE.exists():
        text = CEDICT_CACHE_FILE.read_text(encoding="utf-8")

    if text is None:
        logger.warning("CC-CEDICT unavailable — proceeding without it")
        return

    parsed = _parse_text(text)
    cedict_vocab.clear()
    cedict_vocab.update(parsed)
    overlaid, missing = _merge_into_hsk_vocab()
    logger.info(
        "CC-CEDICT loaded: %d entries (overlaid onto %d HSK words; %d HSK words had no CC-CEDICT match)",
        len(cedict_vocab),
        overlaid,
        missing,
    )


__all__ = ["load_cedict", "CEDICT_CACHE_FILE"]
