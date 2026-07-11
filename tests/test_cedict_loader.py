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


def test_parser_resolves_used_in_pointer_to_target_meaning():
    """儡's only sense is "used in 傀儡[kui3 lei3]" -- a bare pointer, not
    a real definition. It should resolve through to 傀儡's actual gloss
    instead of displaying the dangling reference."""
    sample = (
        "儡 儡 [lei3] /used in 傀儡[kui3 lei3]/\n傀儡 傀儡 [kui3 lei3] /(lit. and fig.) puppet/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["儡"]["meaning"] == "(lit. and fig.) puppet"


def test_parser_resolves_used_in_pointer_through_a_chain():
    """峨嵋 is a variant of 峨眉, and 嵋 alone is "used in 峨嵋" -- two
    levels of indirection. 嵋 should resolve all the way through to
    峨眉's real terminal text, not stop one hop short at 峨嵋's own
    unresolved "variant of" pointer."""
    sample = (
        "嵋 嵋 [mei2] /used in 峨嵋[E2 mei2]/\n"
        "峨嵋 峨嵋 [E2 mei2] /variant of 峨眉[E2 mei2]/\n"
        "峨眉 峨眉 [E2 mei2] /(used in place names, notably 峨眉山[E2 mei2 Shan1] Mount Emei in Sichuan)/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    expected = "(used in place names, notably 峨眉山 (é méi shān) Mount Emei in Sichuan)"
    assert parsed["嵋"]["meaning"] == expected
    assert parsed["峨嵋"]["meaning"] == expected


def test_preferred_reading_override_wins_regardless_of_heuristic_score(monkeypatch):
    """汉's rich Han4 entry (Han ethnic group / Chinese language / the
    Han dynasty) loses to its bare han4 "man" entry under the heuristic
    alone -- the capitalized-pinyin proper-noun penalty (added to stop
    Apple-the-company beating apple-the-fruit) fires on 汉 too, since
    CC-CEDICT capitalizes pinyin for named concepts generally. The
    hand-curated override should force Han4 to win outright."""
    monkeypatch.setattr(
        cedict_loader,
        "_load_primary_overrides",
        lambda: {"preferred_reading": {"汉": "Han4"}, "preferred_sense": {}},
    )
    sample = (
        "漢 汉 [Han4] /Han ethnic group/Chinese (language)/the Han dynasty (206 BC-220 AD)/\n"
        "漢 汉 [han4] /man/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["汉"]["meaning"] == "Han ethnic group"


def test_preferred_sense_override_picks_a_later_sense_in_the_winning_entry(monkeypatch):
    """韩's single Han2 entry lists four senses in etymology-first order
    -- "one of the Seven Hero States of the Warring States" comes before
    "Korea, esp. South Korea" -- and _pick_learner_primary has no signal
    to reorder them since none carry a register tag. The override picks
    the later, everyday sense by substring match."""
    monkeypatch.setattr(
        cedict_loader,
        "_load_primary_overrides",
        lambda: {"preferred_reading": {}, "preferred_sense": {"韩": "Korea, esp. South Korea"}},
    )
    sample = (
        "韓 韩 [Han2] /Han, one of the Seven Hero States of the Warring States "
        "戰國七雄|战国七雄/Korea from the fall of the Joseon dynasty in 1897/"
        "Korea, esp. South Korea 大韓民國|大韩民国/surname Han/\n"
    )
    parsed = cedict_loader._parse_text(sample)
    assert parsed["韩"]["meaning"].startswith("Korea, esp. South Korea")


def test_preferred_sense_override_no_ops_when_substring_does_not_match(monkeypatch):
    """If CC-CEDICT's wording ever shifts, the override should silently
    fall back to the heuristic's normal pick rather than crash or leave
    the entry unset."""
    monkeypatch.setattr(
        cedict_loader,
        "_load_primary_overrides",
        lambda: {"preferred_reading": {}, "preferred_sense": {"韩": "this text will never match"}},
    )
    sample = "韓 韩 [Han2] /Korea/surname Han/\n"
    parsed = cedict_loader._parse_text(sample)
    assert parsed["韩"]["meaning"] == "Korea"


def test_missing_override_file_leaves_heuristic_behaviour_unchanged(monkeypatch, tmp_path):
    """A missing/unreadable override file must degrade gracefully to
    heuristic-only behaviour, not crash the whole CEDICT load."""
    import app.services.cedict_loader as module

    monkeypatch.setattr(
        module,
        "__file__",
        str(tmp_path / "nonexistent_dir" / "cedict_loader.py"),
    )
    result = cedict_loader._load_primary_overrides()
    assert result == {"preferred_reading": {}, "preferred_sense": {}}


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
