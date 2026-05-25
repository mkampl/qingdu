"""
CC-CEDICT loader — parsing + tone-mark conversion + HSK overlay.

We don't exercise the network here; the public entry point is covered
indirectly by integration. Focus is on the pure-Python pieces: tone
conversion, parsing, and the HSK-overlay merge.
"""

from app.services import cedict_loader
from app.state import cedict_vocab, hsk_vocab


def test_tone_conversion_basic_a():
    # 'ni3 hao3' -> 'nǐ hǎo'
    assert cedict_loader._convert_pinyin("ni3 hao3") == "nǐ hǎo"


def test_tone_conversion_priority_a_then_e_then_o():
    # 'gao1' (a beats nothing), 'lei4' (e wins over i), 'kou3' (o wins over u)
    assert cedict_loader._apply_tone("gao1") == "gāo"
    assert cedict_loader._apply_tone("lei4") == "lèi"
    assert cedict_loader._apply_tone("kou3") == "kǒu"


def test_tone_conversion_neutral_drops_digit():
    assert cedict_loader._apply_tone("de5") == "de"
    assert cedict_loader._apply_tone("ma0") == "ma"


def test_tone_conversion_handles_u_umlaut():
    # CC-CEDICT writes ü as 'u:' or 'v'.
    assert cedict_loader._apply_tone("lu:e4") == "lüè"
    assert cedict_loader._apply_tone("nv3") == "nǚ"


def test_parser_extracts_meanings_drops_classifier_lines():
    sample = (
        "# header line that should be ignored\n"
        "傳統 传统 [chuan2 tong3] /tradition/convention/heritage/CL:個|个[ge4]/\n"
        "好 好 [hao3] /good/well/proper/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert "传统" in parsed
    assert parsed["传统"]["meaning"] == "tradition"
    # The CL:... entry must not leak into meanings.
    assert parsed["传统"]["meanings"] == ["tradition", "convention", "heritage"]
    assert parsed["传统"]["traditional"] == "傳統"
    assert parsed["传统"]["pinyin"] == "chuán tǒng"
    assert "好" in parsed
    assert parsed["好"]["meanings"] == ["good", "well", "proper"]


def test_parser_prefers_real_gloss_over_surname_collision():
    """If two readings share a simplified form, prefer the non-surname one."""
    sample = (
        "張 张 [Zhang1] /surname Zhang/\n張 张 [zhang1] /to open up/to spread/sheet of paper/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["张"]["meaning"] == "to open up"


def test_parser_demotes_bare_suffix_marker_against_content_reading():
    """地 (de, "-ly" suffix marker) vs 地 (di4, "earth") — content reading
    wins because the de entry's primary is a pure suffix marker with no
    semantic content."""
    sample = (
        "地 地 [de5] /-ly/structural particle: used before a verb or adjective/\n"
        "地 地 [di4] /earth/ground/field/place/land/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["地"]["meaning"] == "earth"
    assert parsed["地"]["pinyin"] == "dì"


def test_parser_preserves_meaningful_particle_against_abbreviation():
    """的 (de, possessive "of") vs 的 (di1, "a taxi; ... (abbr. for 的士)")
    — the possessive particle has real semantic content; the abbreviation
    should lose despite the file ordering or the neutral tone."""
    sample = (
        "的 的 [de5] /of/possessive particle/(used after an attribute)/\n"
        "的 的 [di1] /a taxi; a cab (abbr. for 的士)/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["的"]["meaning"] == "of"


def test_pure_marker_entry_still_wins_against_surname_only():
    """Sanity: a "-ly"-style bare marker still beats a surname placeholder
    because surnames are penalised harder."""
    sample = "X X [X1] /surname X/\nX X [x5] /-ly/\n"
    parsed = cedict_loader._parse_text(sample)
    assert parsed["X"]["meaning"] == "-ly"


def test_merge_overlays_meanings_on_existing_hsk_entries():
    # Snapshot + clear shared dicts so the test is hermetic.
    original_hsk = dict(hsk_vocab)
    original_cedict = dict(cedict_vocab)
    hsk_vocab.clear()
    cedict_vocab.clear()
    try:
        # Simulate the 地 case: HSK source has the particle-reading pinyin
        # but our CC-CEDICT primary-pick chose the content reading. Both
        # pinyin AND meaning need to come from CC-CEDICT or the displayed
        # gloss would mismatch the rendered reading.
        hsk_vocab["地"] = {
            "pinyin": "de",
            "meaning": "-ly",
            "meanings": ["-ly"],
            "level_new": "new-1",
        }
        cedict_vocab["地"] = {
            "pinyin": "dì",
            "meaning": "earth",
            "meanings": ["earth", "ground", "field"],
            "traditional": "地",
        }
        overlaid, missing = cedict_loader._merge_into_hsk_vocab()
        assert overlaid == 1
        assert missing == 0
        # Meaning + meanings come from CC-CEDICT.
        assert hsk_vocab["地"]["meaning"] == "earth"
        assert hsk_vocab["地"]["meanings"] == ["earth", "ground", "field"]
        # Pinyin now also tracks the CC-CEDICT reading so it matches the
        # gloss we just overlaid.
        assert hsk_vocab["地"]["pinyin"] == "dì"
        # Level info from HSK is preserved.
        assert hsk_vocab["地"]["level_new"] == "new-1"
    finally:
        hsk_vocab.clear()
        hsk_vocab.update(original_hsk)
        cedict_vocab.clear()
        cedict_vocab.update(original_cedict)
