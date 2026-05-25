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


def test_parser_prefers_content_reading_over_particle_reading():
    """地 (de, particle) vs 地 (di4, earth) — content reading wins even
    though the particle entry comes first in CC-CEDICT's file order."""
    sample = (
        "地 地 [de5] /-ly/structural particle: used before a verb or adjective/\n"
        "地 地 [di4] /earth/ground/field/place/land/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["地"]["meaning"] == "earth"
    assert parsed["地"]["pinyin"] == "dì"


def test_parser_prefers_full_tone_over_neutral_tone():
    """Neutral-tone-only readings are usually grammatical particles; the
    content reading should win even if both have legitimate-looking glosses."""
    sample = (
        "了 了 [le5] /(modal particle intensifying preceding clause)/\n"
        "了 了 [liao3] /to finish/to understand clearly/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["了"]["meaning"] == "to finish"


def test_particle_only_entry_still_wins_against_surname_only(monkeypatch):
    """Sanity: when the only alternative is a surname placeholder, a
    particle entry still wins (better than nothing)."""
    sample = "X X [X1] /surname X/\nX X [x5] /(used as a placeholder particle)/\n"
    parsed = cedict_loader._parse_text(sample)
    assert "(used" in parsed["X"]["meaning"]


def test_merge_overlays_meanings_on_existing_hsk_entries():
    # Snapshot + clear shared dicts so the test is hermetic.
    original_hsk = dict(hsk_vocab)
    original_cedict = dict(cedict_vocab)
    hsk_vocab.clear()
    cedict_vocab.clear()
    try:
        hsk_vocab["好"] = {
            "pinyin": "hǎo",
            "meaning": "good (HSK)",
            "meanings": ["good (HSK)"],
            "level_new": "new-1",
        }
        cedict_vocab["好"] = {
            "pinyin": "hǎo",
            "meaning": "good",
            "meanings": ["good", "well", "proper"],
            "traditional": "好",
        }
        overlaid, missing = cedict_loader._merge_into_hsk_vocab()
        assert overlaid == 1
        assert missing == 0
        # The HSK entry should now carry the CC-CEDICT meanings, not the
        # original placeholder.
        assert hsk_vocab["好"]["meaning"] == "good"
        assert hsk_vocab["好"]["meanings"] == ["good", "well", "proper"]
        # Level info from HSK is preserved.
        assert hsk_vocab["好"]["level_new"] == "new-1"
    finally:
        hsk_vocab.clear()
        hsk_vocab.update(original_hsk)
        cedict_vocab.clear()
        cedict_vocab.update(original_cedict)
