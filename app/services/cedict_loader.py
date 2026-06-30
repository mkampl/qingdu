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
    """Convert space-separated numbered pinyin to space-separated tone-marked.

    Erhua suffix (`r5`) is glued onto the preceding syllable: "yi1 kuai4 r5"
    → "yī kuàir" rather than "yī kuài r". CC-CEDICT marks erhua as a
    standalone "r5" syllable, but for display "kuàir" reads naturally and
    "kuài r" reads as a separate phantom syllable.
    """
    syllables = numbered.strip().split()
    out: list[str] = []
    for s in syllables:
        s_low = s.lower()
        if s_low == "r5" and out:
            out[-1] = out[-1] + "r"
        else:
            out.append(_apply_tone(s_low))
    return " ".join(out)


# --- gloss cleanup for display ------------------------------------------------
#
# Raw CC-CEDICT glosses encode cross-references in a lexicographer-friendly
# but learner-hostile format:
#   "erhua form of 女孩[nu:3 hai2]"
#   "the Great Learning, one of the Four Books 四書|四书[Si4 shu1] in Confucianism"
#   "road; path (CL:條|条[tiao2],股[gu3])"
# We rewrite the inline brackets to a rendered pinyin in parens, collapse
# the trad|simp alternative to just the simplified form, drop classifier
# annotations, and cap at the first ~3 semicolon-separated senses so the
# display column doesn't run away with 150-char paragraphs. The lexico-
# graphic detail is still present in the underlying CC-CEDICT data; this
# is purely a display layer.

_CL_INLINE_RE = re.compile(r"\s*\(CL:[^)]*\)")
_TRAD_SIMP_RE = re.compile(r"([一-鿿]+)\|([一-鿿]+)")
_BRACKET_PINYIN_RE = re.compile(r"\[([^\]]+)\]")
_MAX_DISPLAY_SENSES = 3
_MAX_DISPLAY_CHARS = 110


def clean_gloss_for_display(meaning: str) -> str:
    """Strip CC-CEDICT lexicographic markup so the gloss is readable in
    the review queue / word popover. Idempotent: clean output passed in
    again yields the same string. Empty input → empty output."""
    if not meaning:
        return meaning
    s = _CL_INLINE_RE.sub("", meaning)
    s = _TRAD_SIMP_RE.sub(r"\2", s)

    def _render_bracket(m: re.Match[str]) -> str:
        try:
            return f" ({_convert_pinyin(m.group(1))})"
        except Exception:
            return ""

    s = _BRACKET_PINYIN_RE.sub(_render_bracket, s)
    s = re.sub(r"\s+", " ", s).strip()
    # Cap to N semicolon-separated senses, ellipsis if there were more.
    parts = [p.strip() for p in s.split(";") if p.strip()]
    if len(parts) > _MAX_DISPLAY_SENSES:
        s = "; ".join(parts[:_MAX_DISPLAY_SENSES]) + "…"
    # Hard length cap — truncate at the last word boundary.
    if len(s) > _MAX_DISPLAY_CHARS:
        cut = s.rfind(" ", 0, _MAX_DISPLAY_CHARS)
        if cut > 0:
            s = s[:cut].rstrip(",;: ") + "…"
    return s


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
    low = primary.lower()
    return (
        low.startswith("surname ")
        or low.startswith("variant of ")
        or low.startswith("old variant of ")
        or low.startswith("erhua variant of ")
    )


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


def _looks_bound_form(primary: str) -> bool:
    """CC-CEDICT marks readings that exist only inside compounds as
    `(bound form) ...`. For a learner browsing a *single character* card,
    a bound-form gloss is almost never what they want — there's usually
    a free-standing reading of the same character that should win.
    Examples we want to demote: 行 "(bound form) row; line" (the haang2
    reading) loses to xíng "to walk; OK"; 中 "(bound form) China; Chinese"
    loses to zhōng "middle; within"."""
    return primary.lower().lstrip().startswith("(bound form)")


def _looks_referential(primary: str) -> bool:
    """Entries whose entire primary gloss is "used in X" point at another
    word without carrying meaning themselves. Examples: 个 "used in 自個兒"
    or 家 "used in 傢伙|家伙". These are referential stubs — there's almost
    always a real semantic reading we should prefer."""
    return primary.lower().lstrip().startswith("used in ")


def _looks_register_only(primary: str) -> bool:
    """Glosses tagged as literary, classical, archaic, or dialect-only
    are usually dead-language or regional readings that lose to the
    standard modern Mandarin meaning of the same character."""
    low = primary.lower().lstrip()
    return (
        low.startswith("(literary)")
        or low.startswith("(classical)")
        or low.startswith("(archaic)")
        or low.startswith("(dialect)")
    )


_GRAMMATICAL_TRIGGERS = (
    "aspect particle",
    "modal particle",
    "possessive particle",
    "structural particle",
    "genitive particle",
    "grammatical particle",
    "particle indicating",
    "particle expressing",
    "particle used",
    "particle for",
    "classical particle",
    "completed action marker",
    "action marker",
    "tense marker",
    "classifier",
    "measure word",
)


def _looks_grammatical_function(primary: str) -> bool:
    """Glosses describing the character's grammatical function — particle,
    marker, classifier, measure word — are the linguistic *function* of
    the character and almost always the meaning a learner needs to see
    first when a character has both content-word and grammatical-function
    readings. Strips the optional leading "(" so both
    "(aspect particle ...)" and "aspect particle indicating ..." match —
    CEDICT styles them inconsistently.

    Examples that should bonus:
      着 zhe5 "aspect particle indicating action in progress..."
      了 le5  "(completed action marker)"
      个 ge4  "(classifier used before a noun ...)"
      的 de5  "(possessive particle)"
    """
    low = primary.lower().lstrip().lstrip("(")
    return any(low.startswith(trigger) for trigger in _GRAMMATICAL_TRIGGERS)


def _entry_quality(
    primary: str, numbered_pinyin: str, frequency: int = 0, num_meanings: int = 1
) -> int:
    """Higher = better headline candidate. Used to resolve collisions
    when CC-CEDICT lists multiple readings of the same simplified form.

    The penalty stack catches the structural marker patterns CC-CEDICT
    uses to flag readings that are usually wrong as a learner headline:
    surnames, "-ly"-style bare markers, abbreviations, (bound form)
    annotations, "used in X" referential stubs, and tagged-register
    (literary / classical / dialect) entries.

    `frequency` is a per-reading corpus frequency hint (higher = more
    common); breaks ties between two otherwise-equally-scored readings
    by favouring the more common one. Defaults to 0 (no preference)
    when the caller doesn't have a frequency table on hand.
    """
    del numbered_pinyin  # kept in the signature for future heuristics
    score = 100
    if _looks_minor(primary):
        score -= 100
    if _looks_pure_marker(primary):
        score -= 80
    if _looks_abbreviation(primary):
        score -= 40
    if _looks_bound_form(primary):
        score -= 60
    if _looks_referential(primary):
        score -= 90
    if _looks_register_only(primary):
        score -= 50
    if _looks_grammatical_function(primary):
        # Big positive — the particle/classifier reading is fundamental
        # for learners and wins even against a multi-sense content-word
        # reading at the same frequency.
        score += 40
    # Frequency tiebreaker — log-scaled, but with a wider band so
    # SUBTLEX's per-reading frequencies cleanly separate "almost never
    # used" (a few hundred) from "everyday" (tens of thousands). Cap
    # at +80 so it can outweigh the sense-count bonus when the
    # high-sense entry is the rare reading (着 zhao1 has 4 senses but
    # is barely used; zhe5 has 1 sense and is the everyday particle).
    if frequency > 0:
        import math

        score += min(80, int(math.log10(max(1, frequency)) * 16))
    # Stub-gloss penalty. A primary that's just a single English noun
    # ("comma", "yes", "earth") with no verb / preposition / multi-sense
    # punctuation is usually a marginal reading: the everyday reading
    # of the same simplified form will spell out 2-3 senses separated
    # by `;` or `,`. The penalty fires only when the gloss is short
    # AND looks like a single noun (no space) so phrases like "to look
    # at" or "to grow" survive. Caps at -25.
    bare = primary.strip().rstrip(".")
    # Affix markers ("-ly", "~ish") are already caught by _looks_pure_marker;
    # don't double-penalise here. The bare-noun rule is for *plain English
    # nouns* like "comma", not for the marker syntax.
    is_affix_marker = bare.startswith("-") or bare.startswith("~")
    if (
        len(bare) <= 10
        and " " not in bare
        and ";" not in bare
        and "," not in bare
        and "(" not in bare
        and not is_affix_marker
    ):
        score -= 25
    # Sense-count bonus. A reading with multiple distinct senses
    # (separated by `/` in CC-CEDICT) is almost always the everyday
    # meaning: 中 zhōng has 4 senses ("within; among; in / middle;
    # center / while (doing sth); during / (dialect) OK; all right"),
    # while 中 zhòng has just one ("to hit (a target)"). Caps at +20
    # so it's a meaningful tiebreaker without overwhelming the
    # structural penalties.
    if num_meanings > 1:
        score += min(20, (num_meanings - 1) * 5)
    return score


def _load_subtlex_char_pinyin() -> dict[str, dict[str, int]]:
    """Load the bundled SUBTLEX-CH per-character / per-reading frequency
    table. Derived from SUBTLEX-CH-WF (Cai & Brysbaert 2010) by
    aggregating each (character, syllable) pair across every word in
    which it appears with that syllable. The result is the closest thing
    we have to "how often does this particular reading of this character
    actually occur in real spoken-Chinese subtitles".

    Shape: {char: {numbered_pinyin: frequency}}. Missing char → empty.

    SUBTLEX-CH is CC-BY-NC-ND for academic redistribution; the derived
    aggregate we bundle here (sums per char/pinyin only, no original
    transcript material) is a legitimate downstream use.
    """
    import json
    from pathlib import Path as _P

    path = _P(__file__).resolve().parent.parent / "data" / "subtlex_char_pinyin_freq.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _per_reading_frequency(
    subtlex: dict[str, dict[str, int]], char: str, numbered_pinyin: str
) -> int:
    """Per-character per-reading SUBTLEX frequency. Sums across the
    word's syllables when the headword is multi-char so the
    disambiguation works for compound entries too. Returns 0 when
    the char/syllable pair is absent (no harm done, the score's other
    terms still dominate)."""
    syllables = numbered_pinyin.strip().split()
    chars = [c for c in char if "一" <= c <= "鿿"]
    if not chars or not syllables or len(chars) != len(syllables):
        return 0
    total = 0
    for c, syl in zip(chars, syllables, strict=False):
        # SUBTLEX uses tone-numbered pinyin like "zhong1"; that matches
        # CC-CEDICT's numbered_pinyin token format exactly.
        total += subtlex.get(c, {}).get(syl, 0)
    return total


def _parse_text(text: str) -> dict[str, dict]:
    """Parse a CC-CEDICT .u8 text into {simplified: entry} dict.

    On collisions (multiple pinyin readings of the same simplified form),
    `_entry_quality` picks the more useful headline reading: content
    words beat particle-only readings, full-tone pinyin beats all-neutral,
    surname / variant-of placeholders lose to anything else, and ties
    are broken by SUBTLEX-CH per-(character, reading) corpus frequency
    so the most-spoken reading wins over the archaic one.
    """
    subtlex = _load_subtlex_char_pinyin()

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
        # SUBTLEX is the strongest signal for "which reading do learners
        # actually meet" — far better than jieba's per-character-summed
        # heuristic at distinguishing e.g. zhe5 (109K, particle) from
        # zhuo2 (103K, "to wear") from zhao2 (103K, ...) inside 着.
        reading_freq = _per_reading_frequency(subtlex, simplified, numbered_pinyin)
        new_quality = _entry_quality(
            primary, numbered_pinyin, reading_freq, num_meanings=len(meanings)
        )
        existing_quality = quality_cache.get(simplified)
        # `<` (not `<=`) so a later entry with equal score doesn't lose
        # to file-order alone. That kept 读 stuck on the dòu "comma"
        # reading because it happened to parse first; with `<` and the
        # frequency tiebreaker the dú reading wins.
        if existing_quality is not None and new_quality < existing_quality:
            continue
        out[simplified] = {
            "traditional": traditional,
            "pinyin": _convert_pinyin(numbered_pinyin),
            # Cleanup happens here — strip CL annotations, rewrite the
            # `字[bracket pinyin]` cross-references as readable pinyin,
            # collapse trad|simp to simp, cap senses + length. Variant
            # resolution below still works because the cleanup preserves
            # the target hanzi (just rewrites the bracket pinyin around
            # it). See clean_gloss_for_display above.
            "meaning": clean_gloss_for_display(primary),
            "meanings": [clean_gloss_for_display(m) for m in meanings],
            "source": CEDICT_SOURCE_TAG,
        }
        quality_cache[simplified] = new_quality
    _resolve_variant_references(out)
    return out


# Matches "erhua variant of X", "variant of X", "old variant of X",
# "see X", "abbr. for X" — the X target uses the CEDICT "trad|simp[pinyin]"
# notation, or just simp if there's no trad form. We pull the simp form
# out and use it as a lookup key.
_VARIANT_REF_RE = re.compile(
    r"^(?:erhua variant of|old variant of|variant of|see|abbr\. for)\s+"
    r"(?:[^|\s\[]+\|)?([^\s\[]+)",
    re.IGNORECASE,
)


def _resolve_variant_references(parsed: dict[str, dict]) -> None:
    """When the primary gloss is *only* a pointer at another entry
    ("erhua variant of 一塊|一块"), follow the pointer and copy the
    target's primary + meanings here. Without this, 一块儿 displays
    "erhua variant of 一塊|一块[yi1 kuai4]" instead of the actual
    meaning "(coll.) together".

    Mutates `parsed` in place. Skips entries whose primary mixes a
    reference with real content (e.g. "abbr. for 中国 / China") —
    those are usable as-is."""
    for entry in parsed.values():
        primary = entry["meaning"]
        m = _VARIANT_REF_RE.match(primary)
        if not m:
            continue
        target_word = m.group(1).strip()
        target = parsed.get(target_word)
        if target is None:
            continue
        if target["meaning"] == primary:
            # Cycle (target also points back here) — leave as-is.
            continue
        entry["meaning"] = target["meaning"]
        entry["meanings"] = list(target["meanings"])


def _merge_into_hsk_vocab() -> tuple[int, int]:
    """For every HSK word also in CC-CEDICT, overlay the richer meanings
    AND the matching pinyin. Pinyin needs to come along because the
    HSK source picks pinyin for whichever reading it had as primary —
    if our CC-CEDICT primary-pick heuristic chose a different reading
    (e.g. 地 dì for "earth" instead of de for the particle) the HSK
    pinyin would be wrong for the displayed meaning.

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
        cedict_pinyin = cedict_entry.get("pinyin")
        if cedict_pinyin:
            hsk_entry["pinyin"] = cedict_pinyin
        overlaid += 1
    return overlaid, missing


# --- public entry point --------------------------------------------------------


async def load_cedict(force_refresh: bool = False) -> None:
    """Populate `cedict_vocab` + merge meanings into `hsk_vocab`.

    Safe to call even if the network is down — we fall back to the cached
    file. If both fail (no cache + no network), CC-CEDICT is just absent
    and the app keeps working on the existing HSK data.

    Honours `QINGDU_SKIP_CEDICT_LOAD=1` as a hard skip. conftest sets
    this in the test suite so CI doesn't pull ~4MB on every run; the
    handful of tests that actually exercise cedict lookups seed
    `cedict_vocab` directly in their own fixtures.
    """
    import os

    if os.environ.get("QINGDU_SKIP_CEDICT_LOAD") == "1":
        logger.info("CC-CEDICT load skipped (QINGDU_SKIP_CEDICT_LOAD=1)")
        return

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
