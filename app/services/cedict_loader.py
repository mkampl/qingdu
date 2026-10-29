"""
CC-CEDICT loader.

Reads the CC-CEDICT snapshot vendored in `app/data/dict/` (see
`app.services.dict_data`), parses each entry and populates
`app.state.cedict_vocab` keyed by simplified form. Then merges the better
meanings into the already-loaded `hsk_vocab` so every downstream consumer
(analyze, review queue, word_info snapshots) sees the richer glosses
without further code changes.

The snapshot is replaced only by `tools/refresh_dictionaries.py`. If the
vendored file is missing, an older `data/cedict_ts.u8` cache is used, and
only if that is missing too do we download mdbg's current export
(`cedict_1_0_ts_utf-8_mdbg.txt.gz`, NOT a .zip — that path 404s).

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
import json
import logging
import math
import os
import re
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.constants import (
    CEDICT_SOURCE_TAG,
    CEDICT_URL,
    HSK_DOWNLOAD_TIMEOUT,
    HSK_RETRY_MAX_WAIT,
    HSK_RETRY_MIN_WAIT,
    MAX_RETRY_ATTEMPTS,
)
from app.core.paths import DATA_DIR
from app.services import dict_data, learner_glosses
from app.services import readings as readings_service
from app.state import cedict_variants, cedict_vocab, hsk_lists_original, hsk_vocab

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
# rule: a or e takes the mark; in "ou" the o does; otherwise the last
# vowel does. The last-vowel case is what puts the mark on the u of "iu"
# (liù, jiǔ) and on the i of "ui" (huí, duì, shuǐ).
_TONE_MARKS = {
    "a": "āáǎà",
    "e": "ēéěè",
    "i": "īíǐì",
    "o": "ōóǒò",
    "u": "ūúǔù",
    "ü": "ǖǘǚǜ",
}
# Vowels that take the mark outright when present, in priority order
# ("ao" → a). "o" also covers "ou" and "uo".
_VOWEL_PRIORITY = ["a", "e", "o"]
_LAST_VOWEL_CANDIDATES = "iuü"


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
    # Find the vowel that takes the mark: a/e/o first, else the last of
    # i/u/ü ("iu" → u, "ui" → i).
    target_index = -1
    for vowel in _VOWEL_PRIORITY:
        idx = body.find(vowel)
        if idx >= 0:
            target_index = idx
            break
    if target_index < 0:
        target_index = max(body.rfind(v) for v in _LAST_VOWEL_CANDIDATES)
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
# annotations, and cap the length so the display column doesn't run away
# with 150-char paragraphs. The input is ONE CC-CEDICT sense (the "/"
# separated unit); the ";" inside it separate near-synonyms of that same
# sense ("many; much; more; a lot of"), so a short sense is shown whole
# and only an over-long one is cut, preferably at a ";" boundary. The
# lexicographic detail is still present in the underlying CC-CEDICT
# data; this is purely a display layer.

_CL_INLINE_RE = re.compile(r"\s*\(CL:[^)]*\)")
# Multi-clause idioms/proverbs are a single trad|simp pair spanning the
# whole phrase (e.g. "一朝被蛇咬，十年怕井繩|一朝被蛇咬，十年怕井绳"), not one
# pair per clause. The class includes the punctuation CC-CEDICT uses
# inside these phrases so each side of the pair is the whole phrase; a
# hanzi-only class would stop at the comma and duplicate a clause.
_TRAD_SIMP_RE = re.compile(r"([一-鿿，。！？、；：]+)\|([一-鿿，。！？、；：]+)")
_BRACKET_PINYIN_RE = re.compile(r"\[([^\]]+)\]")
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
        inner = m.group(1)
        # Some CC-CEDICT mirrors / re-exports inject spurious spaces
        # around the umlaut colon and tone digit: "nu : 3 hai2" instead
        # of the canonical "nu:3 hai2". Normalize them back so the
        # tone-mark converter sees a well-formed token.
        inner = re.sub(r"\s*:\s*", ":", inner)
        inner = re.sub(r"([a-zü:]+)\s+([1-5])\b", r"\1\2", inner)
        try:
            return f" ({_convert_pinyin(inner)})"
        except Exception:
            return ""

    s = _BRACKET_PINYIN_RE.sub(_render_bracket, s)
    s = re.sub(r"\s+", " ", s).strip()
    return _truncate_gloss(s)


def _truncate_gloss(s: str) -> str:
    """Cap a gloss at _MAX_DISPLAY_CHARS (ellipsis included). Cuts after
    the last whole ";" part that fits; falls back to the last word
    boundary when even the first part is too long. Output never exceeds
    the cap, so a second pass leaves it unchanged."""
    if len(s) <= _MAX_DISPLAY_CHARS:
        return s
    budget = _MAX_DISPLAY_CHARS - 1  # room for the ellipsis
    parts = [p.strip() for p in s.split(";") if p.strip()]
    kept: list[str] = []
    for part in parts:
        candidate = "; ".join([*kept, part])
        if len(candidate) > budget:
            break
        kept.append(part)
    if kept:
        return "; ".join(kept) + "…"
    cut = s.rfind(" ", 0, budget)
    if cut > 0:
        return s[:cut].rstrip(",;: ") + "…"
    return s[:budget] + "…"


# --- headline cleanup ---------------------------------------------------------
#
# The headline ("meaning") is what a learner reads first on a card or in
# the popover; the full senses ("meanings") stay untouched. CC-CEDICT
# opens many senses with a register tag ("(bound form) male", "(coll.)
# father; dad") or an editorial note ("(third-person singular) (since the
# early 20th century, usu. male) he; him; his"), and some end in a long
# usage note ("you (Note: In Taiwan, 妳 is used ...)"). The headline drops
# all of these; the register tags are handed back separately so the UI
# can show them as a small badge next to the headline.

# Leading tags that become a badge. Kept to register/usage labels; domain
# labels like "(physics)" or qualifiers like "(of a person)" stay inline
# because they change what the gloss means.
_HEADLINE_BADGE_TAGS = frozenset(
    {
        "bound form",
        "coll.",
        "literary",
        "classical",
        "archaic",
        "dialect",
        "old",
        "tcm",
        "slang",
        "vulgar",
        "erhua-only",
        "idiom",
        "loanword",
        "formal",
        "informal",
        "honorific",
        "polite",
        "humble",
        "derog.",
        "onom.",
        "euphemism",
    }
)
# Leading notes that are dropped from the headline outright (no badge).
_HEADLINE_EDITORIAL_RE = re.compile(
    r"^(?:(?:first|second|third)-person (?:singular|plural)|since\b.*|note:.*)$",
    re.IGNORECASE,
)
# A leading parenthetical longer than this is an editorial note, not a tag,
# unless it says what the word applies to ("(of markets, industries ...)
# rising") or how it is used grammatically ("(after a noun N and before a
# predicate P)", "(classical particle similar to 于)"); those stay inline.
_HEADLINE_EDITORIAL_MIN_CHARS = 30
_HEADLINE_KEEP_NOTE_RE = re.compile(
    r"^(?:of|after|before|followed by)\b|particle|classifier|prefix|suffix|marker",
    re.IGNORECASE,
)
# A trailing parenthetical is a usage note dropped from the headline when
# it starts with "Note:" or when keeping it would push the headline past
# the display cap (it would be cut off mid-note anyway). Shorter ones
# ("to leave (the stage, an exam room ...)") stay: they carry meaning.
_LEADING_PAREN_RE = re.compile(r"^\(([^()]*)\)\s*")
_TRAILING_PAREN_RE = re.compile(r"\s*\(([^()]*)\)$")
_HAS_WORD_RE = re.compile(r"[A-Za-z]{2,}")


def split_headline(gloss: str) -> tuple[str, list[str]]:
    """Split a sense into (headline text, register tags).

    "(bound form) male" → ("male", ["bound form"]);
    "(third-person singular) (since ..., usu. male) he; him; his" →
    ("he; him; his", []). A prefix or note is only removed while real
    text remains after it, so a sense that is nothing but a parenthetical
    ("(prefix indicating ordinal number ...)") is returned unchanged.
    Works on raw CC-CEDICT text and on clean_gloss_for_display output,
    and is idempotent."""
    if not gloss:
        return gloss, []
    s = gloss.strip()
    tags: list[str] = []
    while True:
        m = _LEADING_PAREN_RE.match(s)
        if not m:
            break
        inner = m.group(1).strip()
        rest = s[m.end() :]
        if not _HAS_WORD_RE.search(rest):
            break
        if inner.lower() in _HEADLINE_BADGE_TAGS:
            if inner.lower() not in (t.lower() for t in tags):
                tags.append(inner)
        elif not (
            _HEADLINE_EDITORIAL_RE.match(inner)
            or (
                len(inner) >= _HEADLINE_EDITORIAL_MIN_CHARS
                and not _HEADLINE_KEEP_NOTE_RE.search(inner)
            )
        ):
            break
        s = rest
    m = _TRAILING_PAREN_RE.search(s)
    if m:
        inner = m.group(1).strip()
        rest = s[: m.start()].rstrip()
        if (
            inner.lower().startswith("note:") or len(s) > _MAX_DISPLAY_CHARS
        ) and _HAS_WORD_RE.search(rest):
            s = rest
    return s, tags


def headline_for_display(gloss: str) -> tuple[str, list[str]]:
    """Display headline for a raw or cleaned sense: tags/notes removed
    (see split_headline), then CC-CEDICT markup cleaned and length capped.
    Returns (headline, tags)."""
    headline, tags = split_headline(gloss)
    return clean_gloss_for_display(headline), tags


_SAME_SENSE_STRIP_RE = re.compile(r"[\s…]+")


def _sense_key(gloss: str) -> str:
    text, _ = split_headline(gloss or "")
    # An over-long sense truncated mid-note leaves an unclosed "(" tail;
    # cut it so it still compares equal to the note-free headline.
    if text.count("(") > text.count(")"):
        text = text[: text.rfind("(")]
    return _SAME_SENSE_STRIP_RE.sub(" ", text).strip(" ;,").lower()


def is_same_sense(headline: str, sense: str) -> bool:
    """True when `sense` (a full entry of `meanings`) is the sense the
    `headline` was derived from — equal after tag/note stripping, or one
    a truncated prefix of the other. Used to list the *other* meanings
    under a headline instead of blindly dropping meanings[0]."""
    a, b = _sense_key(headline), _sense_key(sense)
    if not a or not b:
        return False
    if a == b:
        return True
    a_cut = (headline or "").rstrip().endswith("…")
    b_cut = (sense or "").rstrip().endswith("…")
    return (a_cut and b.startswith(a)) or (b_cut and a.startswith(b))


def cap_meanings(headline: str, meanings: list[str], max_others: int) -> list[str]:
    """Keep the sense(s) the headline came from plus the first
    `max_others` other senses, in dictionary order. The cap counts only
    the *other* senses, so a headline picked from deep in the list
    (男, 上) doesn't push an alternative out or get cut off itself."""
    out: list[str] = []
    others = 0
    for m in meanings:
        if is_same_sense(headline, m):
            out.append(m)
        elif others < max_others:
            out.append(m)
            others += 1
    return out


# --- file fetch + parse --------------------------------------------------------


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


_VARIANT_MARKER_RE = re.compile(r"variant of\s+([^\[\s]+)", re.IGNORECASE)


def _any_sense_self_variant(meanings: list[str], simplified: str) -> bool:
    """True when any sense marks this whole entry as a variant of / old
    form of a DIFFERENT traditional character that happens to collapse to
    the SAME simplified form we're filing this entry under — i.e. this
    line is a redundant duplicate of a reading we already have elsewhere.
    Whether the phrasing leads the sense ("variant of 年[nian2]") or
    trails in a parenthetical ("foolish; stupid (variant of 呆[dai1])")
    doesn't matter; what matters is the target.

    Scoped to *self*-references on purpose. An entry whose real, primary
    reading is fine but whose SECONDARY sense happens to describe an
    unrelated variant relationship for a different word must not be
    penalised for it: 繭 (cocoon)'s second sense is "(bound form) callus
    (variant of 趼[jian3])" — 趼 is a different character entirely, not
    a duplicate of 繭 — so a same-target check leaves 繭 unflagged, where
    a bare "any sense contains variant of" check would demote it below
    蠒, a pure "variant of 繭|茧" stub with no real content of its own.

    A leading-only check (`_looks_minor`, prefix match on the picked
    *primary*) misses the parenthetical-trailing form: 呆's own third
    sense "variant of 待[dai1]" is not a self-reference (待 isn't 呆), but
    獃's "foolish; stupid (variant of 呆[dai1])" is, and would let 獃
    outrank 呆."""
    for m in meanings:
        match = _VARIANT_MARKER_RE.search(m)
        if match and simplified in match.group(1):
            return True
    return False


# Register / usage tags that CC-CEDICT prefixes to senses. Any sense
# starting with one of these is dispreferred for a learner-facing primary
# — it either isn't the everyday reading (archaic/literary) or doesn't
# stand alone as a word (bound form).
_DEPRIORITISE_TAGS = (
    "(literary)",
    "(classical)",
    "(archaic)",
    "(dialect)",
    "(bound form)",
    "(tcm)",  # technical, e.g. 号's "to feel (the pulse) (used in ...)"
    "(vulgar)",
    "(slang)",
    "(coll.)",  # colloquial CC-CEDICT tag — still usable but not primary
    "(old)",
    "(erhua-only)",
)

_LEADING_PARENS_RE = re.compile(r"^(?:\([^)]*\)\s*)+")

# A bare alternate-pronunciation cross-reference CC-CEDICT sometimes
# appends as its own sense — "Taiwan pr. [ji1]" or "also pr. [yi4]" —
# with no register tag and no semantic content of its own.
_PRONUNCIATION_NOTE_RE = re.compile(r"^(?:also|taiwan)\s+pr\.\s*[\[(]", re.IGNORECASE)


def _has_deprioritised_tag(sense: str) -> bool:
    """True when the sense's leading parenthetical annotation cluster
    contains a register/usage tag from _DEPRIORITISE_TAGS. CC-CEDICT
    sometimes stacks a domain tag ahead of the register tag —
    "(computing) (bound form) parent-" for 父 — so a startswith() on just
    the first tag would miss the (bound form) marker and let the
    domain-jargon sense win as primary. Collects every leading "(...)"
    group and checks the tag list against all of them."""
    low = sense.lower().lstrip()
    m = _LEADING_PARENS_RE.match(low)
    if not m:
        return False
    leading = m.group(0)
    return any(tag in leading for tag in _DEPRIORITISE_TAGS)


def _looks_pronunciation_note(sense: str) -> bool:
    """True for a bare "Taiwan pr. [x]" / "also pr. [x]" cross-reference.
    These carry no meaning of their own and don't open with a register
    tag, so without this check a character whose every real sense is
    tagged would fall through to the footnote (迹 "Taiwan pr. (jī)"
    instead of "trace; mark")."""
    return bool(_PRONUNCIATION_NOTE_RE.match(sense.strip()))


def _pick_learner_primary(meanings: list[str]) -> str:
    """CC-CEDICT often orders senses etymology-first, so `meanings[0]` for
    多义-heavy characters like 号 can be a literary reading buried under
    the everyday one ("(literary) to call out; to command" ahead of "day
    of the month"). Pick the first sense that doesn't carry a register
    tag from _DEPRIORITISE_TAGS (see _has_deprioritised_tag for the
    compound-tag case) and isn't a bare pronunciation cross-reference.
    Falls back to `meanings[0]` when every sense is disqualified (e.g.
    purely-classical characters — no winning move).

    Idempotent + no lookahead — only sees the meanings we're passed.
    Runs before clean_gloss_for_display, so the input still has raw
    CC-CEDICT markup."""
    if not meanings:
        return ""
    for sense in meanings:
        if _has_deprioritised_tag(sense) or _looks_pronunciation_note(sense):
            continue
        return sense
    return meanings[0]


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
    "question particle",
    "sentence-final particle",
    "particle equivalent",
    "completed action marker",
    "action marker",
    "tense marker",
    "classifier",
    "measure word",
)


# Characters whose particle/classifier reading earns the grammatical
# bonus in _entry_quality.
_PARTICLE_CHARS = frozenset("了的着地得吧吗呢个啊呀啦嘛哦")
_FREQUENCY_POINTS_PER_DECADE = 32


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
    primary: str,
    numbered_pinyin: str,
    frequency: int = 0,
    meanings: list[str] | None = None,
    simplified: str = "",
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

    `meanings` is the full sense list for this entry (defaults to just
    `[primary]` for callers that only have the headline). Used for the
    variant/surname check below and the sense-count bonus. `simplified`
    is the simplified form this entry is filed under — needed by the
    self-variant check (see `_any_sense_self_variant`) to tell "this
    line duplicates a reading we already have" from "this line merely
    mentions an unrelated character's variant relationship."
    """
    meanings = meanings if meanings is not None else [primary]
    score = 100
    # CC-CEDICT capitalizes the pinyin of proper-noun readings
    # ("Ping2 guo3" the company vs "ping2 guo3" the fruit); the company's
    # long gloss dodges every other penalty, so without this one 苹果 would
    # read "Apple (American tech company)". When a word only HAS
    # proper-noun readings (中国), they all carry the penalty and the
    # relative ranking still works.
    if numbered_pinyin[:1].isupper():
        score -= 70
    # Scan every sense, not just the picked primary. 秊 (a variant
    # character of 年) lists "grain / harvest (old) / variant of 年" and
    # _pick_learner_primary grabs "grain", so a primary-only check would
    # miss the marker and let 秊's 3-sense padding outscore 年's single
    # "year" via the sense-count bonus below (likewise 驩 vs 歡 for 欢).
    # _any_sense_self_variant also catches the marker when it trails a
    # sense in a parenthetical, scoped to self-references so an unrelated
    # variant mention in a secondary sense doesn't demote an otherwise
    # fine entry (see its docstring).
    if _looks_minor(primary) or _any_sense_self_variant(meanings, simplified):
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
    if simplified in _PARTICLE_CHARS and _looks_grammatical_function(primary):
        # The particle reading of a real particle (了 le, 着 zhe, 个 gè)
        # is the one a learner needs first, even against a content-word
        # reading at the same frequency. Limited to these characters: a
        # classifier sense anywhere else is usually the rare reading
        # (服 fù "dose", 通 tòng, 只 zhī) and must not get a boost.
        score += 40
    # Frequency, log-scaled and uncapped: a cap would tie both everyday
    # readings of common characters (好 hǎo vs hào), exactly where the
    # signal matters most. 32 points per decade fits best against
    # pypinyin's phrase readings for all HSK words with several readings.
    if frequency > 0:
        score += int(math.log10(frequency) * _FREQUENCY_POINTS_PER_DECADE)
    # Sense-count bonus. A reading with multiple distinct senses
    # (separated by `/` in CC-CEDICT) is almost always the everyday
    # meaning: 中 zhōng has 4 senses ("within; among; in / middle;
    # center / while (doing sth); during / (dialect) OK; all right"),
    # while 中 zhòng has just one ("to hit (a target)"). Caps at +20
    # so it's a meaningful tiebreaker without overwhelming the
    # structural penalties.
    if len(meanings) > 1:
        score += min(20, (len(meanings) - 1) * 5)
    return score


def _load_subtlex_char_pinyin() -> dict[str, dict[str, int]]:
    """Load the bundled SUBTLEX-CH per-character / per-reading frequency
    table. Derived from SUBTLEX-CH-WF (Cai & Brysbaert 2010) by
    aggregating each (character, syllable) pair across every word in
    which it appears with that syllable. The result is the closest thing
    we have to "how often does this particular reading of this character
    actually occur in real spoken-Chinese subtitles".

    Shape: {char: {numbered_pinyin: frequency}}. Missing char → empty.

    SUBTLEX-CH is free academic-download data (the underlying word-frequency
    files are PLOS ONE Supporting Information, published CC BY); the derived
    aggregate we bundle here (sums per char/pinyin only, no original
    transcript material) is a legitimate downstream use. See
    THIRD_PARTY_LICENSES.md for the full provenance writeup.
    """
    path = Path(__file__).resolve().parent.parent / "data" / "subtlex_char_pinyin_freq.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _load_primary_overrides() -> dict[str, dict[str, str]]:
    """Load the hand-curated primary-sense/reading override list (see
    app/data/cedict_primary_overrides.json for provenance and the
    rationale for keeping this manual rather than trying to make the
    heuristic scoring perfect for every one of CC-CEDICT's ~120k entries).

    Shape: {"preferred_reading": {simplified: numbered_pinyin}, "preferred_sense": {simplified: substring}}.
    Missing/unparseable file -> both empty, heuristic-only behaviour unchanged.
    """
    path = Path(__file__).resolve().parent.parent / "data" / "cedict_primary_overrides.json"
    if not path.exists():
        return {"preferred_reading": {}, "preferred_sense": {}}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {
            "preferred_reading": data.get("preferred_reading", {}),
            "preferred_sense": data.get("preferred_sense", {}),
        }
    except Exception:
        return {"preferred_reading": {}, "preferred_sense": {}}


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

    Every distinct reading of a simplified form is kept in
    `entry["readings"]` (one per pinyin, case-insensitive; when several
    lines share a pinyin, the best-scored line stands for it). The top
    level of the entry (`pinyin`, `meaning`, `meaning_tags`, `meanings`)
    mirrors the main reading.

    The main reading of an HSK word is anchored on its HSK-list and
    pypinyin readings (see app.services.readings). For every other word,
    and for HSK words where anchoring finds nothing, `_entry_quality`
    picks it: content words beat particle-only readings, full-tone pinyin
    beats all-neutral, surname / variant-of placeholders lose to anything
    else, and SUBTLEX-CH per-(character, reading) frequency weighs in so
    the most-spoken reading wins over the archaic one.
    """
    subtlex = _load_subtlex_char_pinyin()
    overrides = _load_primary_overrides()
    preferred_reading = overrides["preferred_reading"]
    preferred_sense = overrides["preferred_sense"]

    # simplified -> {lower-case numbered pinyin -> best line for it}
    grouped: dict[str, dict[str, dict]] = {}
    for order, raw_line in enumerate(text.splitlines()):
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
        # Prefer the first non-register-tagged sense as the primary so
        # everyday readings don't lose to CC-CEDICT's etymology-first
        # ordering (see _pick_learner_primary).
        primary = _pick_learner_primary(meanings)
        # SUBTLEX is the strongest signal for "which reading do learners
        # actually meet" — far better than jieba's per-character-summed
        # heuristic at distinguishing e.g. zhe5 (109K, particle) from
        # zhuo2 (103K, "to wear") from zhao2 (103K, ...) inside 着.
        reading_freq = _per_reading_frequency(subtlex, simplified, numbered_pinyin)
        quality = _entry_quality(
            primary, numbered_pinyin, reading_freq, meanings=meanings, simplified=simplified
        )
        # Hand-curated reading override wins outright, structural score
        # notwithstanding. E.g. 汉's rich Han4 entry ("Han ethnic group /
        # Chinese language / the Han dynasty") loses to its bare han4
        # "man" entry under the heuristic alone -- the capitalized-pinyin
        # proper-noun penalty (see _entry_quality) fires on 汉 too, since CC-CEDICT capitalizes pinyin
        # for named concepts generally, not just irrelevant proper nouns.
        if preferred_reading.get(simplified) == numbered_pinyin:
            quality = 10_000_000
        group = grouped.setdefault(simplified, {})
        key = numbered_pinyin.lower()
        existing = group.get(key)
        # `<` (not `<=`) so a later line with an equal score doesn't lose
        # to file order alone.
        if existing is not None and quality < existing["quality"]:
            continue
        headline, headline_tags = headline_for_display(primary)
        group[key] = {
            "traditional": traditional,
            "numbered": numbered_pinyin,
            "quality": quality,
            "stub": _looks_stub_reading(primary, simplified),
            "order": order,
            # Cleanup happens here — strip CL annotations, rewrite the
            # `字[bracket pinyin]` cross-references as readable pinyin,
            # collapse trad|simp to simp, cap senses + length. Variant
            # resolution below still works because the cleanup preserves
            # the target hanzi (just rewrites the bracket pinyin around
            # it). See clean_gloss_for_display above.
            # The headline also loses register tags and editorial notes
            # (see split_headline); the tags travel in meaning_tags and
            # the full senses stay in meanings.
            "reading": {
                "pinyin": _convert_pinyin(numbered_pinyin),
                "primary": headline,
                "meaning_tags": headline_tags,
                "meanings": [clean_gloss_for_display(m) for m in meanings],
                "is_main": False,
            },
        }

    anchors = _hsk_reading_anchors()
    reading_overrides = readings_service.load_reading_overrides()
    out: dict[str, dict] = {}
    for simplified, group in grouped.items():
        lines = list(group.values())
        # Highest score wins; on a tie the later line does, which keeps 读
        # off the dòu "comma" reading that happens to be listed first.
        main = max(lines, key=lambda c: (c["quality"], c["order"]))
        pinned = preferred_reading.get(simplified)
        if (
            simplified in anchors
            and len(lines) > 1
            and not (pinned and any(c["numbered"] == pinned for c in lines))
        ):
            picked = readings_service.pick_main_reading(
                simplified,
                [(c["numbered"], c["quality"], c["stub"]) for c in lines],
                anchors[simplified],
                reading_overrides.get(simplified),
            )
            if picked is not None:
                main = lines[picked]
        ordered = [main] + sorted(
            (c for c in lines if c is not main), key=lambda c: (-c["quality"], c["order"])
        )
        for c in ordered:
            c["reading"]["is_main"] = c is main
        out[simplified] = {
            "traditional": main["traditional"],
            "source": CEDICT_SOURCE_TAG,
            "readings": [c["reading"] for c in ordered],
        }
    # Hand-curated sense override, for entries where the *reading* already
    # won correctly but CC-CEDICT's etymology-first sense ordering within
    # that one entry buries the everyday meaning behind an obscure one --
    # e.g. 韩's single Han2 entry lists "one of the Seven Hero States of
    # the Warring States" before "Korea, esp. South Korea". Matches by
    # substring against the already-cleaned senses so it survives
    # clean_gloss_for_display's markup stripping; silently no-ops if
    # CC-CEDICT's wording ever shifts enough to break the match, rather
    # than crashing or reintroducing the raw markup. Applied to every
    # reading the substring matches, so it holds whichever reading ends
    # up main.
    for simplified, wanted_substring in preferred_sense.items():
        entry = out.get(simplified)
        if entry is None:
            continue
        for reading in entry["readings"]:
            match = next((s for s in reading["meanings"] if wanted_substring in s), None)
            if match is not None:
                reading["primary"], reading["meaning_tags"] = headline_for_display(match)
    _resolve_variant_references(out)
    # Reviewed learner headlines replace CC-CEDICT's on the main reading
    # only; senses and other readings stay (see app.services.learner_glosses).
    learner_glosses.apply_to_parsed(out, learner_glosses.load_learner_glosses())
    for entry in out.values():
        _sync_main_reading(entry)
    _attach_reading_examples(out)
    return out


def _variant_forms(text: str, parsed: dict[str, dict]) -> dict[str, str]:
    """{traditional form: simplified headword} for every form that only
    appears in CC-CEDICT's traditional column, so text written with it
    (玅, a variant of 妙) still finds the entry."""
    forms: dict[str, str] = {}
    for raw_line in text.splitlines():
        m = _ENTRY_RE.match(raw_line.strip())
        if not m:
            continue
        traditional, simplified = m.group(1), m.group(2)
        if traditional != simplified and traditional not in parsed and simplified in parsed:
            forms.setdefault(traditional, simplified)
    return forms


def _looks_stub_reading(primary: str, simplified: str) -> bool:
    """A reading that is never the main one while a real reading
    matches: a pointer at another reading of the same word ("see
    過來|过来[guo4 lai2]" on 过来 guò lai), a reading that only occurs
    inside one compound ("used in 似的[shi4 de5]" on 似 shì), and, for a
    compound, a bare grammatical note ("(verb suffix)" on 过去 guò qu).
    Single characters keep their parenthesised particle readings (了 le
    "(completed action marker)")."""
    m = _VARIANT_REF_RE.match(primary)
    if m and m.group(1).strip() == simplified:
        return True
    if _looks_referential(primary):
        return True
    text = primary.strip()
    return (
        len(simplified) > 1 and text.startswith("(") and text.endswith(")") and text.count("(") == 1
    )


def _sync_main_reading(entry: dict) -> None:
    """Copy the main reading onto the entry's top-level fields."""
    main = next((r for r in entry["readings"] if r["is_main"]), entry["readings"][0])
    entry["pinyin"] = main["pinyin"]
    entry["meaning"] = main["primary"]
    entry["meaning_tags"] = list(main["meaning_tags"])
    entry["meanings"] = main["meanings"]


def _hsk_reading_anchors() -> dict[str, str | None]:
    """{HSK word: its HSK-list pinyin} for anchoring the main reading.
    Component characters (no list entry of their own) map to None, so only
    pypinyin anchors them. Read from `hsk_lists_original`, which keeps the
    list's own pinyin even after the CC-CEDICT overlay rewrote
    `hsk_vocab`."""
    anchors: dict[str, str | None] = {}
    for word, entry in hsk_vocab.items():
        original = hsk_lists_original.get(word)
        if original is not None:
            anchors[word] = original.get("pinyin") or None
        elif entry.get("is_original_hsk"):
            anchors[word] = entry.get("pinyin") or None
        else:
            anchors[word] = None
    return anchors


def _attach_reading_examples(parsed: dict[str, dict]) -> None:
    """Give each reading of a polyphone character a usage example: the
    most basic HSK word that reads the character that way (长 zhǎng →
    校长). Stored as {word, pinyin, meaning} on the reading, or None."""
    if not hsk_vocab:
        return
    index = readings_service.build_example_index(parsed, hsk_vocab)
    for simplified, entry in parsed.items():
        if len(simplified) != 1 or len(entry["readings"]) < 2:
            continue
        for reading in entry["readings"]:
            syllables = readings_service.numbered_syllables(reading["pinyin"])
            word = index.get((simplified, syllables[0])) if syllables else None
            example = parsed.get(word) if word else None
            reading["example"] = (
                {"word": word, "pinyin": example["pinyin"], "meaning": example["meaning"]}
                if example
                else None
            )


# Matches "erhua variant of X", "erhua form of X", "variant of X",
# "old variant of X", "see X", "abbr. for X", "used in X" — the X target
# uses the CEDICT "trad|simp[pinyin]" notation, or just simp if there's
# no trad form. We pull the simp form out and use it as a lookup key.
#
# `erhua form of` and `erhua variant of` are interchangeable in the
# source; both are needed so 女孩儿 (`erhua form of 女孩[nu:3 hai2]`)
# shows "girl", not the pointer. `used in X` covers readings like 漂's
# piao4 ("used in 漂亮[piao4 liang5]"), which rightly outscores piao1
# "to float" on frequency and is then followed to 漂亮's meaning
# ("pretty").
#
# The cleaned headline renders the target's bracket pinyin as "(pīn
# yīn)" right after it; group 2 captures that so a pointer can be
# followed to the right reading of a polyphone target.
_VARIANT_REF_RE = re.compile(
    r"^(?:erhua (?:variant|form) of|old variant of|variant of|see|abbr\. for|used in)\s+"
    r"(?:[^|\s\[]+\|)?([^\s\[(]+)(?:\s*\(([^)]*)\))?",
    re.IGNORECASE,
)


def _target_reading(
    entry: dict, wanted_pinyin: str | None, exclude: dict | None = None
) -> dict | None:
    """The reading of `entry` a pointer refers to: the one whose pinyin
    matches the pointer's, else the main reading. `exclude` (the pointing
    reading itself, for a self-reference) is never returned."""
    candidates = [r for r in entry["readings"] if r is not exclude]
    if not candidates:
        return None
    wanted = readings_service.numbered_syllables(wanted_pinyin)
    if wanted:
        for r in candidates:
            strength = readings_service.match_strength(
                wanted, readings_service.numbered_syllables(r["pinyin"])
            )
            if strength == readings_service.STRONG_MATCH:
                return r
    return next((r for r in candidates if r["is_main"]), candidates[0])


def _resolve_variant_references(parsed: dict[str, dict]) -> None:
    """When a reading's primary gloss is *only* a pointer at another entry
    ("erhua variant of 一塊|一块"), follow the pointer and copy the
    target's primary + meanings here. Without this, 一块儿 displays
    "erhua variant of 一塊|一块[yi1 kuai4]" instead of the actual
    meaning "(coll.) together".

    A pointer at the same headword ("see 血[xue4]" on 血 xiě, "see
    儘快|尽快[jin3 kuai4]" on 尽快 jìn kuài) resolves to the other
    reading it names. Pointers at other polyphones follow the bracket
    pinyin too, falling back to the target's main reading.

    Runs to a fixed point (capped) rather than a single pass so chained
    pointers (A -> B -> C) resolve fully instead of leaving A on B's
    still-unresolved text; the target of a "used in X" stub is often
    itself a variant of another entry.

    "used in X" on a reading other than the main one stays as written:
    "gě: used in 自个儿" says more than 自个儿's gloss would.

    Mutates `parsed` in place. Skips readings whose primary mixes a
    reference with real content (e.g. "abbr. for 中国 / China") —
    those are usable as-is."""
    for _ in range(5):
        changed = False
        for simplified, entry in parsed.items():
            for reading in entry["readings"]:
                primary = reading["primary"]
                m = _VARIANT_REF_RE.match(primary)
                if not m:
                    continue
                if not reading["is_main"] and primary.lower().startswith("used in "):
                    # An other reading that only occurs inside one word
                    # (个 gě in 自个儿) reads better as the pointer than
                    # as that word's gloss.
                    continue
                target_word = m.group(1).strip()
                target_entry = parsed.get(target_word)
                if target_entry is None:
                    continue
                own = reading if target_word == simplified else None
                target = _target_reading(target_entry, m.group(2), exclude=own)
                if target is None or target["primary"] == primary:
                    # Cycle (target also points back here) — leave as-is.
                    continue
                reading["primary"] = target["primary"]
                reading["meaning_tags"] = list(target.get("meaning_tags") or [])
                reading["meanings"] = list(target["meanings"])
                changed = True
        if not changed:
            break


def _merge_into_hsk_vocab() -> tuple[int, int]:
    """For every HSK word also in CC-CEDICT, overlay the richer meanings,
    the matching pinyin and all readings. Pinyin needs to come along
    because the HSK source picks pinyin for whichever reading it had as
    primary — if the anchored main reading differs (e.g. 读 dú instead of
    the list's dòu "comma") the HSK pinyin would be wrong for the
    displayed meaning.

    Returns (overlaid_count, missing_count) for logging.
    """
    overlaid = 0
    missing = 0
    glosses = learner_glosses.load_learner_glosses()
    for word, hsk_entry in hsk_vocab.items():
        cedict_entry = cedict_vocab.get(word)
        if not cedict_entry:
            missing += 1
            learner_glosses.apply_to_hsk_only(word, hsk_entry, glosses)
            continue
        hsk_entry["meaning"] = cedict_entry["meaning"]
        hsk_entry["meaning_tags"] = list(cedict_entry.get("meaning_tags") or [])
        hsk_entry["meanings"] = cedict_entry["meanings"]
        if cedict_entry.get("readings"):
            hsk_entry["readings"] = cedict_entry["readings"]
        cedict_pinyin = cedict_entry.get("pinyin")
        if cedict_pinyin:
            hsk_entry["pinyin"] = cedict_pinyin
        overlaid += 1
    return overlaid, missing


# --- public entry point --------------------------------------------------------


async def load_cedict() -> None:
    """Populate `cedict_vocab` + merge meanings into `hsk_vocab`.

    Normally reads the vendored snapshot and touches no network. If no
    copy exists anywhere, CC-CEDICT is just absent and the app keeps
    working on the existing HSK data.

    Honours `QINGDU_SKIP_CEDICT_LOAD=1` as a hard skip. conftest sets
    this in the test suite to keep it fast; the tests that exercise
    cedict lookups seed `cedict_vocab` directly in their own fixtures.
    """
    if os.environ.get("QINGDU_SKIP_CEDICT_LOAD") == "1":
        logger.info("CC-CEDICT load skipped (QINGDU_SKIP_CEDICT_LOAD=1)")
        return

    dict_data.loaded_sources["cedict"] = None
    text: str | None = None
    digest: str | None = None

    vendored = None
    try:
        vendored = dict_data.read_vendored("cedict")
    except (dict_data.ChecksumError, OSError, ValueError) as e:
        logger.error("Vendored CC-CEDICT unusable: %s", e)
    if vendored is not None:
        data, digest = vendored
        text = data.decode("utf-8")
    elif CEDICT_CACHE_FILE.exists():
        logger.warning("Vendored CC-CEDICT missing; using cache %s", CEDICT_CACHE_FILE)
        data = CEDICT_CACHE_FILE.read_bytes()
        digest = dict_data.sha256_bytes(data)
        text = data.decode("utf-8")
    else:
        try:
            logger.warning("No CC-CEDICT on disk; downloading unpinned %s", CEDICT_URL)
            data = gzip.decompress(await _download_archive())
            digest = dict_data.sha256_bytes(data)
            text = data.decode("utf-8")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            CEDICT_CACHE_FILE.write_bytes(data)
        except Exception as e:  # noqa: BLE001
            logger.warning("CC-CEDICT download failed (%s)", e)

    if text is None:
        logger.warning("CC-CEDICT unavailable — proceeding without it")
        return

    parsed = _parse_text(text)
    cedict_vocab.clear()
    cedict_vocab.update(parsed)
    cedict_variants.clear()
    cedict_variants.update(_variant_forms(text, parsed))
    overlaid, missing = _merge_into_hsk_vocab()
    dict_data.loaded_sources["cedict"] = digest
    logger.info(
        "CC-CEDICT loaded: %d entries (overlaid onto %d HSK words; %d HSK words had no CC-CEDICT match)",
        len(cedict_vocab),
        overlaid,
        missing,
    )


__all__ = ["load_cedict", "CEDICT_CACHE_FILE"]
