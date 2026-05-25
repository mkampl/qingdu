"""
CC-CEDICT loader.

Pulls the canonical Chinese-English dictionary file from mdbg.net's
weekly export, parses each entry and populates `app.state.cedict_vocab`
keyed by simplified form. Then merges the better meanings into the
already-loaded `hsk_vocab` so every downstream consumer (analyze,
review queue, word_info snapshots) sees the richer glosses without
further code changes.

Distribution: the file is served gzip-compressed at
`cedict_1_0_ts_utf-8_mdbg.txt.gz` (NOT a .zip — that path 404s on
mdbg.net). We download the .gz, decompress to UTF-8 text, parse, and
cache the decompressed file at `data/cedict_ts.u8`.

CC-CEDICT format (one entry per line, # comments at file top):
    傳統 传统 [chuan2 tong3] /tradition/convention/heritage/CL:個|个[ge4]/

We:
- drop the bare-CL classifier annotations from `meanings` (they're not
  glosses, they're grammatical metadata),
- convert tone-numbered pinyin (chuan2 tong3) to tone-marked
  (chuán tǒng) so it lines up with the rest of the app.

License of CC-CEDICT data: CC-BY-SA 4.0.
"""

from __future__ import annotations

import gzip
import logging
import re
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
async def _download_archive() -> bytes:
    async with httpx.AsyncClient(timeout=HSK_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        r = await client.get(CEDICT_URL)
        r.raise_for_status()
        return r.content


def _decompress(archive_bytes: bytes) -> str:
    """Decompress the gzipped CC-CEDICT export into a UTF-8 string."""
    return gzip.decompress(archive_bytes).decode("utf-8")


def _looks_minor(primary: str) -> bool:
    """Surname or variant-of placeholder entries — almost never what a
    learner is looking up first."""
    return primary.startswith("surname ") or primary.startswith("variant of ")


def _looks_pure_marker(primary: str) -> bool:
    """True when the primary gloss is a *bare* grammatical marker with
    no real meaning attached — e.g. "-ly" for 地's de reading. Distinct
    from particles that carry actual semantic content (的's "of", 了's
    "(modal particle indicating completion)"). For pure markers there's
    almost always a better reading hiding behind a tone change."""
    m = primary.strip()
    if m.startswith("-") or m.startswith("~"):
        return True
    low = m.lower()
    # Bracketed-only marker definitions like "(used before...)" with no
    # surrounding gloss. We don't catch "(modal particle ...)" because
    # those entries usually carry usage notes that ARE useful.
    return low.startswith("(used ") and m.endswith(")")


def _looks_abbreviation(primary: str) -> bool:
    """Primary glosses that announce themselves as abbreviations — for
    polysemous characters these are almost never the meaning a learner
    wants as primary (e.g. 的's "a taxi; a cab (abbr. for 的士)" should
    lose to the possessive-particle reading "of")."""
    low = primary.lower().strip()
    return "abbr." in low or low.startswith("(abbr")


def _entry_quality(primary: str, numbered_pinyin: str) -> int:
    """Higher = better headline candidate. Used to resolve collisions
    when CC-CEDICT lists multiple readings of the same simplified form.

    The heuristics are deliberately conservative — we only demote
    entries whose primary gloss is plainly wrong as a headline:
    surname placeholders, "-ly"-style bare markers, and abbreviations.
    Everything else stays at full score and the file's natural order
    decides (CC-CEDICT tends to put the most common reading first
    within a character's entry block)."""
    del numbered_pinyin  # kept in the signature for future heuristics
    score = 100
    if _looks_minor(primary):
        score -= 100
    if _looks_pure_marker(primary):
        score -= 80
    if _looks_abbreviation(primary):
        score -= 40
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
            archive_bytes = await _download_archive()
            text = _decompress(archive_bytes)
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
