"""Display layer for CC-CEDICT glosses: tone-mark placement, headline
cleanup (register tags / editorial notes) and the length cap."""

import pytest

from app.services import cedict_loader

_MARKS = {"i": "īíǐì", "u": "ūúǔù"}

_IU_INITIALS = ["d", "j", "l", "m", "n", "q", "x"]
_UI_INITIALS = ["d", "g", "h", "k", "r", "s", "t", "z", "c", "ch", "sh", "zh"]


@pytest.mark.parametrize("tone", [1, 2, 3, 4])
@pytest.mark.parametrize("initial", _IU_INITIALS)
def test_apply_tone_marks_u_in_iu(initial, tone):
    expected = f"{initial}i{_MARKS['u'][tone - 1]}"
    assert cedict_loader._apply_tone(f"{initial}iu{tone}") == expected


@pytest.mark.parametrize("tone", [1, 2, 3, 4])
@pytest.mark.parametrize("initial", _UI_INITIALS)
def test_apply_tone_marks_i_in_ui(initial, tone):
    expected = f"{initial}u{_MARKS['i'][tone - 1]}"
    assert cedict_loader._apply_tone(f"{initial}ui{tone}") == expected


@pytest.mark.parametrize(
    ("numbered", "marked"),
    [
        ("hao3", "hǎo"),
        ("xie4", "xiè"),
        ("guo2", "guó"),
        ("lu:e4", "lüè"),
        ("nv3", "nǚ"),
        ("nu:3", "nǚ"),
        ("er2", "ér"),
        ("kou3", "kǒu"),
        ("zhuang1", "zhuāng"),
        ("xiong2", "xióng"),
        ("yue4", "yuè"),
        ("you3", "yǒu"),
        ("wei4", "wèi"),
        ("lü4", "lǜ"),
        ("jun1", "jūn"),
        ("yi1", "yī"),
        ("wu3", "wǔ"),
        ("m2", "m"),
        ("de5", "de"),
    ],
)
def test_apply_tone_regressions(numbered, marked):
    assert cedict_loader._apply_tone(numbered) == marked


def test_convert_pinyin_ui_words():
    assert cedict_loader._convert_pinyin("hui2 da2") == "huí dá"
    assert cedict_loader._convert_pinyin("shui4 jiao4") == "shuì jiào"
    assert cedict_loader._convert_pinyin("yi1 hui4 r5") == "yī huìr"
    assert cedict_loader._convert_pinyin("jiu3") == "jiǔ"


# --- headline cleanup ---------------------------------------------------------


@pytest.mark.parametrize(
    ("gloss", "headline", "tags"),
    [
        ("(bound form) male", "male", ["bound form"]),
        ("(bound form) up; upper; above; previous", "up; upper; above; previous", ["bound form"]),
        (
            "(third-person singular) (since the early 20th century, usu. male) he; him; his",
            "he; him; his",
            [],
        ),
        ("(coll.) father; dad", "father; dad", ["coll."]),
        ("(literary) (of moonlight) dim", "(of moonlight) dim", ["literary"]),
        ("(formal) (honorific) your writing", "your writing", ["formal", "honorific"]),
        (
            "you (Note: In Taiwan, 妳 is used to address females, but in mainland China, "
            "it is not commonly used. Instead, 你 is used to address both males and females.)",
            "you",
            [],
        ),
        # Qualifiers and grammatical notes change the meaning; they stay.
        ("(of a person) tall", "(of a person) tall", []),
        (
            "(of markets, industries, infectious diseases etc) rising",
            "(of markets, industries, infectious diseases etc) rising",
            [],
        ),
        ("(after a verb) a bit; a little", "(after a verb) a bit; a little", []),
        ("(physics) force", "(physics) force", []),
        # A sense that is only a parenthetical is left alone.
        (
            '(prefix indicating ordinal number, as in 第六[di4 liu4] "sixth")',
            '(prefix indicating ordinal number, as in 第六[di4 liu4] "sixth")',
            [],
        ),
        ("(bound form)", "(bound form)", []),
        # A short trailing note is part of the sense.
        (
            "to leave (the stage, an exam room, the playing field etc)",
            "to leave (the stage, an exam room, the playing field etc)",
            [],
        ),
        ("water", "water", []),
        ("", "", []),
    ],
)
def test_split_headline(gloss, headline, tags):
    assert cedict_loader.split_headline(gloss) == (headline, tags)


def test_split_headline_is_idempotent():
    once, _ = cedict_loader.split_headline("(coll.) (bound form) father; dad")
    assert cedict_loader.split_headline(once) == (once, [])


def test_long_trailing_note_dropped_when_it_would_be_truncated():
    raw = (
        "to think; to believe (often with the implication that the belief is "
        "mistaken – unless referring to one's own current belief)"
    )
    assert cedict_loader.headline_for_display(raw) == ("to think; to believe", [])


# --- length cap -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("many; much; more; a lot of", "many; much; more; a lot of"),
        (
            "some; a few; a little; (following an adjective) slightly ...er",
            "some; a few; a little; (following an adjective) slightly ...er",
        ),
        ("also; too; as well; (not ...) either", "also; too; as well; (not ...) either"),
        (
            "gate; door; doorway; gateway; opening (CL:扇[shan4])",
            "gate; door; doorway; gateway; opening",
        ),
    ],
)
def test_clean_gloss_keeps_short_sense_whole(raw, expected):
    assert cedict_loader.clean_gloss_for_display(raw) == expected


def test_clean_gloss_cuts_long_sense_at_part_boundary():
    raw = "; ".join(f"meaning number {i}" for i in range(20))
    out = cedict_loader.clean_gloss_for_display(raw)
    assert out.endswith("…")
    assert len(out) <= cedict_loader._MAX_DISPLAY_CHARS
    assert out[:-1].split("; ")[-1].startswith("meaning number")
    assert cedict_loader.clean_gloss_for_display(out) == out


def test_clean_gloss_cuts_single_long_part_at_word_boundary():
    raw = " ".join(["word"] * 60)
    out = cedict_loader.clean_gloss_for_display(raw)
    assert out.endswith("word…")
    assert len(out) <= cedict_loader._MAX_DISPLAY_CHARS
    assert cedict_loader.clean_gloss_for_display(out) == out


# --- same-sense matching --------------------------------------------------------


@pytest.mark.parametrize(
    ("headline", "sense", "same"),
    [
        ("male", "(bound form) male", True),
        (
            "he; him; his",
            "(third-person singular) (since the early 20th century) he; him; his",
            True,
        ),
        ("you", "you (Note: In Taiwan, 妳 is used to address females, but in mainland…", True),
        ("to think; to believe", "to think; to believe (often with the implication…", True),
        ("up; upper; above…", "(bound form) up; upper; above; previous", True),
        ("water", "water", True),
        ("water", "(after a name) ... River", False),
        ("male", "baron, the lowest of the five ranks", False),
        ("", "water", False),
    ],
)
def test_is_same_sense(headline, sense, same):
    assert cedict_loader.is_same_sense(headline, sense) is same


# --- golden spot checks on real CC-CEDICT lines ---------------------------------

_SAMPLE = """\
回 回 [Hui2] /Hui ethnic group (Chinese Muslims)/
回 回 [hui2] /to go back; to return; to turn back; to turn around/to reply; to answer/classifier for occurrences or times/
對 对 [dui4] /right; correct/towards; at; for/concerning; regarding/to treat (sb a certain way)/
水 水 [Shui3] /surname Shui/Shui ethnic group/
水 水 [shui3] /water/(after a name) ... River/(coll.) lacking in substance; shoddy/
男 男 [nan2] /(bound form) male/baron, the lowest of the five ranks of nobility 五等爵位[wu3 deng3 jue2 wei4]/
上 上 [shang4] /(bound form) up; upper; above; previous/first (of multiple parts)/to climb; to get onto; to go up/
他 他 [ta1] /(third-person singular) (since the early 20th century, usu. male) he; him; his/(bound form) other; another; some other (as in 他日[ta1 ri4] and 他人[ta1 ren2])/
妳 你 [ni3] /you (Note: In Taiwan, 妳 is used to address females, but in mainland China, it is not commonly used. Instead, 你 is used to address both males and females.)/
多 多 [duo1] /many; much; more; a lot of/too many; in excess/(after a numeral) ... odd/
一些 一些 [yi1 xie1] /some; a few; a little; (following an adjective) slightly ...er/
也 也 [ye3] /also; too; as well; (not ...) either/(literary) particle having functions similar to 啊[a5]/
門 门 [men2] /gate; door; doorway; gateway; opening (CL:扇[shan4])/valve; switch/
爸爸 爸爸 [ba4 ba5] /(coll.) father; dad/CL:位[wei4]/
"""


@pytest.fixture
def golden(monkeypatch):
    monkeypatch.setattr(
        cedict_loader,
        "_load_primary_overrides",
        lambda: {
            "preferred_reading": {},
            "preferred_sense": {"男": "male", "上": "up; upper; above"},
        },
    )
    return cedict_loader._parse_text(_SAMPLE)


@pytest.mark.parametrize(
    ("word", "pinyin", "meaning", "tags"),
    [
        ("回", "huí", "to go back; to return; to turn back; to turn around", []),
        ("对", "duì", "right; correct", []),
        ("水", "shuǐ", "water", []),
        ("男", "nán", "male", ["bound form"]),
        ("上", "shàng", "up; upper; above; previous", ["bound form"]),
        ("他", "tā", "he; him; his", []),
        ("你", "nǐ", "you", []),
        ("多", "duō", "many; much; more; a lot of", []),
        ("一些", "yī xiē", "some; a few; a little; (following an adjective) slightly ...er", []),
        ("也", "yě", "also; too; as well; (not ...) either", []),
        ("门", "mén", "gate; door; doorway; gateway; opening", []),
        ("爸爸", "bà ba", "father; dad", ["coll."]),
    ],
)
def test_golden_headlines(golden, word, pinyin, meaning, tags):
    entry = golden[word]
    assert entry["pinyin"] == pinyin
    assert entry["meaning"] == meaning
    assert entry["meaning_tags"] == tags


def test_meanings_keep_full_sense_text(golden):
    assert golden["男"]["meanings"][0] == "(bound form) male"
    assert golden["他"]["meanings"][0].startswith("(third-person singular)")


def test_merge_carries_meaning_tags(golden, monkeypatch):
    from app import state

    monkeypatch.setattr(state, "cedict_vocab", dict(golden))
    monkeypatch.setattr(cedict_loader, "cedict_vocab", state.cedict_vocab)
    hsk = {"男": {"pinyin": "nan2", "meaning": "male", "meanings": ["male"]}}
    monkeypatch.setattr(cedict_loader, "hsk_vocab", hsk)
    cedict_loader._merge_into_hsk_vocab()
    assert hsk["男"]["meaning"] == "male"
    assert hsk["男"]["meaning_tags"] == ["bound form"]


def test_analyze_payload_carries_meaning_tags(monkeypatch):
    import asyncio

    from app import state
    from app.services import segmentation

    entry = {
        "pinyin": "nán",
        "meaning": "male",
        "meanings": ["(bound form) male"],
        "meaning_tags": ["bound form"],
        "level": "1",
        "level_new": "new-1",
        "level_old": "old-1",
        "frequency": 1,
    }
    monkeypatch.setitem(state.hsk_vocab, "男", entry)
    result = asyncio.run(segmentation.analyze_chinese_text("男"))
    word = next(w for w in result["words"] if w["text"] == "男")
    assert word["meaning"] == "male"
    assert word["meaning_tags"] == ["bound form"]
