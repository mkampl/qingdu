"""Polyphone readings: main-reading anchoring for HSK words, all readings
kept on the CC-CEDICT entry, self-"see" pointers, usage examples, the
scorer fixes, and the `readings` payload on analyze / review / vocab."""

import asyncio

import pytest

from app import state
from app.services import cedict_loader, readings

# These tests check the CC-CEDICT selection itself, under the learner glosses.
pytestmark = pytest.mark.usefixtures("no_learner_glosses")

# --- pinyin normalisation -------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("dōng xi", ("dong1", "xi5")),
        ("dong1 xi5", ("dong1", "xi5")),
        ("Hǎo", ("hao3",)),
        ("nǚ rén", ("nv3", "ren2")),
        ("nu:3 ren2", ("nv3", "ren2")),
        ("yī huìr", ("yi1", "hui4", "r5")),
        ("yi1 hui4 r5", ("yi1", "hui4", "r5")),
        ("ér", ("er2",)),
        ("le", ("le5",)),
        ("bù yīhuǐr5", None),  # run-together HSK-list junk
        ("", None),
        (None, None),
    ],
)
def test_numbered_syllables(text, expected):
    assert readings.numbered_syllables(text) == expected


def test_phrase_reading_uses_phrase_dictionary_and_erhua():
    assert readings.phrase_reading("好吃") == ("hao3", "chi1")
    assert readings.phrase_reading("当时") == ("dang1", "shi2")
    assert readings.phrase_reading("一会儿") == ("yi1", "hui4", "r5")


def test_match_strength_neutral_tone_is_weak():
    n = readings.numbered_syllables
    assert readings.match_strength(n("dōng xi"), n("dōng xi")) == readings.STRONG_MATCH
    assert readings.match_strength(n("dōng xi"), n("dōng xī")) == readings.WEAK_MATCH
    assert readings.match_strength(n("dōng xī"), n("dòng xī")) == readings.NO_MATCH
    assert readings.match_strength(n("hǎo"), n("hǎo chī")) == readings.NO_MATCH


# --- pick_main_reading ------------------------------------------------------------


def test_anchor_follows_agreeing_hsk_and_pypinyin_over_scorer():
    # 好: the scorer may prefer hào; both anchors say hǎo.
    cands = [("hao3", 200, False), ("hao4", 300, False)]
    assert readings.pick_main_reading("好", cands, "hǎo") == 0


def test_anchor_disagreement_is_settled_by_the_scorer():
    # HSK list says gě (its first form), pypinyin gè: best score wins.
    cands = [("ge3", 10, False), ("ge4", 250, False), ("Ge4", 100, False)]
    assert readings.pick_main_reading("个", cands, "gě") == 1


def test_anchor_override_wins():
    cands = [("chang2", 200, False), ("zhang3", 300, False)]
    assert readings.pick_main_reading("长", cands, "cháng", override="zhǎng") == 1
    assert readings.pick_main_reading("长", cands, None) == 1  # pypinyin: zhǎng
    # An override CC-CEDICT doesn't have is ignored.
    assert readings.pick_main_reading("长", cands, None, override="cāng") == 1


def test_anchor_without_any_match_keeps_scorer_pick():
    assert readings.pick_main_reading("好", [("xx1", 1, False), ("yy2", 2, False)], "zz3") is None


def test_compound_prefers_neutral_tone_reading_but_not_all_neutral_or_stub():
    # 东西: both anchors give dōng xī; dōng xi "thing" is the word.
    cands = [("dong1 xi1", 300, False), ("dong1 xi5", 200, False)]
    assert readings.pick_main_reading("东西", cands, "dōng xī") == 1
    # 起来: qi lai (complement, no full tone) loses to qǐ lai.
    cands = [("qi3 lai5", 200, False), ("qi5 lai5", 300, False)]
    assert readings.pick_main_reading("起来", cands, "qǐ lai") == 0
    # 过来: guò lai only points back at guò lái.
    cands = [("guo4 lai2", 200, False), ("guo4 lai5", 300, True)]
    assert readings.pick_main_reading("过来", cands, "guò lái") == 0


def test_single_character_has_no_neutral_preference():
    cands = [("na3", 300, False), ("na5", 100, False)]
    assert readings.pick_main_reading("哪", cands, "nǎ") == 0


def test_stub_never_anchors():
    # pypinyin reads 似 as shì, which CC-CEDICT has only as "used in 似的".
    cands = [("shi4", 100, True), ("si4", 250, False)]
    assert readings.pick_main_reading("似", cands, None) is None


def test_load_reading_overrides(tmp_path):
    path = tmp_path / "o.json"
    path.write_text('{"readings": {"个": {"pinyin": "gè", "why": "x"}, "x": {}}}', "utf-8")
    assert readings.load_reading_overrides(path) == {"个": "gè"}
    assert readings.load_reading_overrides(tmp_path / "missing.json") == {}


def test_bundled_reading_overrides_are_valid():
    overrides = readings.load_reading_overrides()
    assert overrides["个"] == "gè"
    for word, pinyin in overrides.items():
        syllables = readings.numbered_syllables(pinyin)
        assert syllables and len(syllables) == len(word), (word, pinyin)


# --- loader: all readings kept, anchored main ---------------------------------------

_SAMPLE = """\
好 好 [hao3] /good/appropriate; proper/all right!/
好 好 [hao4] /to be fond of; to have a tendency to; to be prone to/
血 血 [xie3] /see 血[xue4]/
血 血 [xue4] /blood/colloquial pr. [xie3]/
儘快 尽快 [jin3 kuai4] /as quickly as possible; as soon as possible/
盡快 尽快 [jin4 kuai4] /see 儘快|尽快[jin3 kuai4]/
個 个 [ge3] /used in 自個兒|自个儿[zi4 ge3 r5]/
個 个 [ge4] /(classifier used before a noun that has no specific classifier)/(bound form) individual/
箇 个 [ge4] /variant of 個|个[ge4]/
長 长 [chang2] /long/(bound form) length/
長 长 [zhang3] /chief/head/elder/to grow/to develop/
長城 长城 [Chang2 cheng2] /the Great Wall/
校長 校长 [xiao4 zhang3] /principal (of school, college or university)/
"""


@pytest.fixture
def parsed(monkeypatch):
    """Parse _SAMPLE with a small HSK vocabulary in place, as startup does."""
    hsk = {
        "好": {"pinyin": "hǎo", "level_new": "new-1", "is_original_hsk": True},
        "个": {"pinyin": "gě", "level_new": "new-1", "is_original_hsk": True},
        "长": {"pinyin": "cháng", "level_new": "new-2", "is_original_hsk": True},
        "血": {"pinyin": "xuè", "level_new": "new-3", "is_original_hsk": True},
        "尽快": {"pinyin": "jǐn kuài", "level_new": "new-4", "is_original_hsk": True},
        "长城": {"pinyin": "Cháng chéng", "level_new": "new-3", "is_original_hsk": True},
        "校长": {
            "pinyin": "xiào zhǎng",
            "level_new": "new-2",
            "is_original_hsk": True,
            "frequency": 3000,
        },
    }
    monkeypatch.setattr(cedict_loader, "hsk_vocab", hsk)
    monkeypatch.setattr(cedict_loader, "hsk_lists_original", {w: dict(e) for w, e in hsk.items()})
    monkeypatch.setattr(
        cedict_loader,
        "_load_primary_overrides",
        lambda: {"preferred_reading": {}, "preferred_sense": {}},
    )
    monkeypatch.setattr(
        cedict_loader,
        "_load_subtlex_char_pinyin",
        # SUBTLEX's noisy counts: hào and zhǎng look more common.
        lambda: {
            "好": {"hao3": 400_000, "hao4": 500_000},
            "长": {"zhang3": 33_698, "chang2": 20_179},
        },
    )
    monkeypatch.setattr(readings, "load_reading_overrides", lambda path=None: {"长": "cháng"})
    return cedict_loader._parse_text(_SAMPLE)


def test_main_reading_is_anchored_and_others_kept(parsed):
    hao = parsed["好"]
    assert (hao["pinyin"], hao["meaning"]) == ("hǎo", "good")
    assert [(r["pinyin"], r["is_main"]) for r in hao["readings"]] == [
        ("hǎo", True),
        ("hào", False),
    ]
    assert hao["readings"][1]["primary"] == "to be fond of; to have a tendency to; to be prone to"


def test_override_pins_main_reading(parsed):
    assert (parsed["长"]["pinyin"], parsed["长"]["meaning"]) == ("cháng", "long")
    assert [r["pinyin"] for r in parsed["长"]["readings"]] == ["cháng", "zhǎng"]


def test_same_pinyin_lines_collapse_to_one_reading(parsed):
    ge = parsed["个"]
    assert ge["pinyin"] == "gè"
    assert [r["pinyin"] for r in ge["readings"]] == ["gè", "gě"]


def test_other_reading_used_in_pointer_is_kept_as_written(parsed):
    other = parsed["个"]["readings"][1]
    assert other["primary"].startswith("used in 自个儿")


def test_self_see_pointer_resolves_to_other_reading(parsed):
    xue = parsed["血"]
    assert (xue["pinyin"], xue["meaning"]) == ("xuè", "blood")
    xie = next(r for r in xue["readings"] if r["pinyin"] == "xiě")
    assert xie["primary"] == "blood"
    jin = parsed["尽快"]
    assert jin["pinyin"] == "jǐn kuài"
    assert all(r["primary"].startswith("as quickly") for r in jin["readings"])


def test_other_reading_gets_usage_example(parsed):
    zhang = next(r for r in parsed["长"]["readings"] if r["pinyin"] == "zhǎng")
    assert zhang["example"] == {
        "word": "校长",
        "pinyin": "xiào zhǎng",
        "meaning": "principal (of school, college or university)",
    }
    chang = parsed["长"]["readings"][0]
    assert chang["example"]["word"] == "长城"


def test_merge_carries_readings(parsed, monkeypatch):
    hsk = {"好": {"pinyin": "hào", "meaning": "x", "meanings": ["x"]}}
    monkeypatch.setattr(cedict_loader, "hsk_vocab", hsk)
    monkeypatch.setattr(cedict_loader, "cedict_vocab", parsed)
    cedict_loader._merge_into_hsk_vocab()
    assert hsk["好"]["pinyin"] == "hǎo"
    assert hsk["好"]["readings"] is parsed["好"]["readings"]


def test_non_hsk_word_uses_scorer_only(monkeypatch):
    monkeypatch.setattr(cedict_loader, "hsk_vocab", {})
    monkeypatch.setattr(cedict_loader, "hsk_lists_original", {})
    monkeypatch.setattr(cedict_loader, "_load_subtlex_char_pinyin", lambda: {})
    out = cedict_loader._parse_text(
        "車 车 [che1] /car/vehicle/machine/\n車 车 [ju1] /war chariot (archaic)/rook (chess)/\n"
    )
    assert out["车"]["pinyin"] == "chē"
    assert len(out["车"]["readings"]) == 2


# --- scorer -----------------------------------------------------------------------


def test_scorer_no_longer_penalises_one_word_glosses():
    # 车 chē "car" lost to jū "war chariot" through the -25 stub penalty.
    car = cedict_loader._entry_quality("car", "che1", 53066, ["car", "vehicle"], "车")
    chariot = cedict_loader._entry_quality(
        "war chariot (archaic)", "ju1", 26109, ["war chariot (archaic)", "rook"], "车"
    )
    assert car > chariot


def test_grammatical_bonus_only_for_real_particles():
    dose = cedict_loader._entry_quality("classifier for medicine: dose", "fu4", 1000, None, "服")
    plain = cedict_loader._entry_quality("dose of medicine", "fu4", 1000, None, "服")
    assert dose == plain
    ge = cedict_loader._entry_quality(
        "(classifier used before a noun that has no specific classifier)", "ge4", 1000, None, "个"
    )
    ge_plain = cedict_loader._entry_quality("individual thing", "ge4", 1000, None, "个")
    assert ge == ge_plain + 40
    ma = cedict_loader._entry_quality(
        '(question particle for "yes-no" questions)', "ma5", 0, None, "吗"
    )
    assert ma == cedict_loader._entry_quality("what?", "ma5", 0, None, "吗") + 40


def test_frequency_bonus_is_not_capped():
    common = cedict_loader._entry_quality("good", "hao3", 4_000_000, None, "好")
    less = cedict_loader._entry_quality("good", "hao3", 400_000, None, "好")
    assert common - less == cedict_loader._FREQUENCY_POINTS_PER_DECADE


# --- API payload ------------------------------------------------------------------


def test_readings_payload_shape_and_main_override(parsed):
    payload = readings.readings_payload(parsed["好"])
    assert [r["pinyin"] for r in payload] == ["hǎo", "hào"]
    assert payload[0]["is_main"] and not payload[1]["is_main"]
    assert set(payload[0]) == {
        "pinyin",
        "primary",
        "meanings",
        "meaning_tags",
        "is_main",
        "example",
    }
    assert payload[0]["example"] is None  # no example for the reading on top
    # A review card stored on hào shows hào on top.
    flipped = readings.readings_payload(parsed["好"], main_pinyin="hào")
    assert [(r["pinyin"], r["is_main"]) for r in flipped] == [("hào", True), ("hǎo", False)]
    # Single-reading words carry nothing.
    assert readings.readings_payload(parsed["校长"]) is None
    assert readings.readings_payload(None) is None


def test_analyze_payload_carries_readings(parsed, monkeypatch):
    from app.services import segmentation

    entry = {
        "pinyin": "hǎo",
        "meaning": "good",
        "meanings": parsed["好"]["meanings"],
        "readings": parsed["好"]["readings"],
        "level": "new-1",
        "level_new": "new-1",
        "level_old": "old-1",
        "frequency": 1,
    }
    monkeypatch.setitem(state.hsk_vocab, "好", entry)
    result = asyncio.run(segmentation.analyze_chinese_text("好"))
    word = next(w for w in result["words"] if w["text"] == "好")
    assert [r["pinyin"] for r in word["readings"]] == ["hǎo", "hào"]


def test_hsk_browse_carries_readings(client, parsed, monkeypatch):
    entry = {
        "pinyin": "hǎo",
        "meaning": "good",
        "meanings": parsed["好"]["meanings"],
        "readings": parsed["好"]["readings"],
        "level": "new-1",
        "level_new": "new-1",
        "is_original_hsk": True,
    }
    monkeypatch.setitem(state.hsk_vocab, "好", entry)
    monkeypatch.setitem(state.hsk_lists_original, "好", entry)
    r = client.get("/api/vocab/hsk", params={"q": "好", "limit": 200})
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["hanzi"] == "好")
    assert [x["pinyin"] for x in item["readings"]] == ["hǎo", "hào"]
