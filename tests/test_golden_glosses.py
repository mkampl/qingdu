"""Golden set: readings and headline glosses for HSK 1-2 words, tricky
polyphones and glue tokens, resolved through the app's own loaders on the
pinned dictionary data (app/data/dict/).

The expectations live in tests/data/golden_glosses.json (see its "about"
block). Entries the code still gets wrong carry an "xfail" field naming
the branch meant to fix them; they run as xfail(strict=True), so a fix
shows up as an XPASS failure until the field is removed from the data.
"""

import json
import re
from pathlib import Path

import pytest
from pypinyin import Style, lazy_pinyin

from app import state
from app.services import cedict_loader, dict_data, hsk_loader
from app.services.word_info import lookup_pinyin_meaning

GOLDEN_FILE = Path(__file__).parent / "data" / "golden_glosses.json"
GOLDEN = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))["entries"]

# Register tags that headline_for_display moves out of the headline.
_TAG_RE = re.compile(r"^\((bound form|coll\.|literary|classical|archaic|dialect|informal)\)", re.I)


def _norm_pinyin(p: str) -> str:
    return re.sub(r"[\s'’-]", "", p or "").lower()


def keyword_in(headline: str, keyword: str) -> bool:
    """Whole-word, case-insensitive match; plural and -ed/-ing endings ok."""
    pattern = r"(?<![a-z])" + re.escape(keyword.lower()) + r"(?:s|es|ed|d|ing)?(?![a-z])"
    return re.search(pattern, (headline or "").lower()) is not None


@pytest.fixture(scope="module")
def pinned_dictionaries():
    """Load the vendored HSK list and CC-CEDICT exactly as startup does,
    then put the previous shared state back."""
    saved = (
        dict(state.hsk_vocab),
        dict(state.hsk_lists_original),
        dict(state.cedict_vocab),
    )
    hsk_raw, _ = dict_data.read_vendored("hsk")
    cedict_raw, _ = dict_data.read_vendored("cedict")
    hsk_loader.process_raw_hsk(json.loads(hsk_raw))
    state.cedict_vocab.clear()
    state.cedict_vocab.update(cedict_loader._parse_text(cedict_raw.decode("utf-8")))
    cedict_loader._merge_into_hsk_vocab()
    state.unknown_word_cache.clear()
    yield
    for target, copy in zip(
        (state.hsk_vocab, state.hsk_lists_original, state.cedict_vocab), saved, strict=True
    ):
        target.clear()
        target.update(copy)
    state.unknown_word_cache.clear()


def _test_id(word: str) -> str:
    # Hanzi would be escaped in test ids; numbered pinyin stays readable.
    return "".join(lazy_pinyin(word, style=Style.TONE3, neutral_tone_with_five=True))


def _params():
    for entry in GOLDEN:
        marks = []
        if entry.get("xfail"):
            marks.append(pytest.mark.xfail(strict=True, reason=f"{entry['xfail']} fixes this"))
        yield pytest.param(entry, id=_test_id(entry["word"]), marks=marks)


@pytest.mark.parametrize("entry", _params())
def test_golden_gloss(entry, pinned_dictionaries):
    word = entry["word"]
    pinyin, meaning = lookup_pinyin_meaning(word)

    if entry.get("expect") == "not_a_word":
        assert " + " not in meaning, f"{word}: glued gloss {meaning!r}"
        return

    allowed = [entry["pinyin"], *entry.get("pinyin_alt", [])]
    assert _norm_pinyin(pinyin) in {_norm_pinyin(p) for p in allowed}, (
        f"{word}: pinyin {pinyin!r}, expected {' / '.join(allowed)}"
    )
    assert any(keyword_in(meaning, k) for k in entry["accept"]), (
        f"{word}: headline {meaning!r} has none of {entry['accept']}"
    )
    if "no-tag" in entry.get("checks", []):
        assert not _TAG_RE.match(meaning), f"{word}: tag left in headline {meaning!r}"


def test_golden_file_is_well_formed():
    words = [e["word"] for e in GOLDEN]
    assert len(words) == len(set(words)), "duplicate words in golden set"
    for e in GOLDEN:
        assert e.get("xfail") in (None, "B6", "B7", "B8"), e
        if e.get("expect") == "not_a_word":
            continue
        assert e["pinyin"] and e["accept"], e


def test_golden_covers_all_hsk_1_2_headwords(pinned_dictionaries):
    """A dictionary refresh that adds HSK 1-2 words must extend the set."""
    covered = {e["word"] for e in GOLDEN}
    hsk_1_2 = {
        w
        for w, e in state.hsk_vocab.items()
        if e.get("is_original_hsk") and (e.get("level_new") or "") in ("new-1", "new-2")
    }
    assert hsk_1_2, "pinned HSK data did not load"
    assert sorted(hsk_1_2 - covered) == []


def test_keyword_matching_rules():
    assert keyword_in("to go to school", "school")
    assert keyword_in("cars; vehicles", "car")
    assert keyword_in("to wear; to put on", "put on")
    assert not keyword_in("to carry", "car")
    assert not keyword_in("passport", "pass")
