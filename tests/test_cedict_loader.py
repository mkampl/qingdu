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


def test_clean_gloss_renders_single_word_trad_simp_pair():
    raw = "傳統|传统[chuan2 tong3]"
    assert cedict_loader.clean_gloss_for_display(raw) == "传统 (chuán tǒng)"


def test_clean_gloss_multi_clause_idiom_trad_simp_pair_not_duplicated():
    """A multi-clause proverb's trad|simp pair spans the whole phrase,
    commas included — not one pair per clause. A hanzi-only character
    class in _TRAD_SIMP_RE stopped at the internal fullwidth comma and
    matched across clause boundaries instead of across the pair
    boundary, duplicating a clause in the output."""
    raw = (
        "see 丈二和尚，摸不著頭腦|丈二和尚，摸不着头脑"
        "[zhang4 er4 he2 shang5 , mo1 bu5 zhao2 tou2 nao3]"
    )
    cleaned = cedict_loader.clean_gloss_for_display(raw)
    assert cleaned == "see 丈二和尚，摸不着头脑 (zhàng èr hé shang , mō bu zháo tóu nǎo)"
    assert cleaned.count("丈二和尚") == 1


def test_parser_prefers_real_word_over_variant_character_padded_with_senses():
    """秊 (a variant character of 年) lists three senses — "grain /
    harvest (old) / variant of 年" — while 年 itself has just one
    ("year"). The stub-gloss penalty hits "year" for being short, and
    the sense-count bonus used to reward 秊's padding enough to win,
    because the "variant of 年" sense sat third and _pick_learner_primary
    only inspects the picked headline, not the full list. 年 (HSK-1!)
    displayed "grain" on review cards until this was caught."""
    sample = "年 年 [nian2] /year/\n秊 年 [nian2] /grain/harvest (old)/variant of 年[nian2]/\n"
    parsed = cedict_loader._parse_text(sample)
    assert parsed["年"]["meaning"] == "year"


def test_parser_prefers_real_word_over_variant_character_trailing_marker():
    """Same bug, marker in a trailing parenthetical instead of leading a
    sense: 驩 (a variant character of 歡|欢) is "a breed of horse /
    variant of 歡|欢" and used to beat 歡's "joyous / happy / pleased"."""
    sample = (
        "歡 欢 [huan1] /joyous/happy/pleased/\n"
        "驩 欢 [huan1] /a breed of horse/variant of 歡|欢[huan1]/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["欢"]["meaning"] == "joyous"


def test_parser_self_variant_check_does_not_penalise_unrelated_cross_reference():
    """呆 has its OWN third sense "variant of 待[dai1]" (呆 is, in some
    contexts, itself a variant of a DIFFERENT character, 待) — that must
    not disqualify 呆 relative to 獃, which is a variant CHARACTER of 呆
    specifically ("(variant of 呆[dai1])" embedded in both its senses).
    A same-target check is what tells these apart; a bare "any sense
    mentions variant of" check flags both equally and lets whichever has
    more padding senses win regardless of which one is the real word."""
    sample = (
        "呆 呆 [dai1] /foolish; stupid/expressionless; blank/variant of 待[dai1]/\n"
        "獃 呆 [dai1] /foolish; stupid (variant of 呆[dai1])/"
        "expressionless; blank (variant of 呆[dai1])/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["呆"]["meaning"] == "foolish; stupid"


def test_parser_self_variant_check_ignores_unrelated_secondary_sense():
    """繭 (cocoon) has a fine primary sense but a SECONDARY sense that
    mentions an unrelated character's variant relationship ("(bound
    form) callus (variant of 趼[jian3])" — 趼 is a different word, not
    a duplicate of 繭). That must not disqualify 繭 against 蠒, a pure
    "variant of 繭|茧" stub with no real content of its own."""
    sample = (
        "繭 茧 [jian3] /(bound form) cocoon/(bound form) callus (variant of 趼[jian3])/\n"
        "蠒 茧 [jian3] /variant of 繭|茧[jian3]/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["茧"]["meaning"] == "(bound form) cocoon"


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


def test_parser_prefers_common_noun_over_proper_noun_collision():
    """苹果 the fruit must beat 苹果 the tech company (2026-07 audit).

    The company's long parenthesised gloss dodges the stub-gloss penalty
    that the fruit's bare "apple" eats, so file order used to decide —
    and drilled "Apple (American tech company)" into HSK-3 review cards.
    CC-CEDICT's capitalized-pinyin convention marks the proper noun.
    """
    sample = (
        "蘋果 苹果 [Ping2 guo3] /Apple (American multinational technology company)/\n"
        "蘋果 苹果 [ping2 guo3] /apple/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["苹果"]["meaning"] == "apple"
    assert parsed["苹果"]["pinyin"] == "píng guǒ"

    # A word whose ONLY readings are proper nouns keeps working — the
    # penalty is relative, not disqualifying.
    only_proper = cedict_loader._parse_text("中國 中国 [Zhong1 guo2] /China/\n")
    assert only_proper["中国"]["meaning"] == "China"


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
