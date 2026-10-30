"""Learner-gloss layer (app/data/learner_glosses.json): it replaces only the
main reading's headline, skips glosses written for another reading, and is
part of the dictionary version. Plus the tools that write and check it."""

import importlib
import json
import logging
import shutil
import sys
from pathlib import Path

import pytest

from app import state
from app.services import cedict_loader, dict_data, learner_glosses

CEDICT = (
    "太 太 [tai4] /highest/greatest/too (much)/very/extremely/\n"
    "教 教 [jiao1] /to teach/\n"
    "教 教 [jiao4] /(bound form) to teach/a religion/\n"
    "好 好 [hao3] /good/well/\n"
    "好 好 [hao4] /to be fond of/\n"
    "上 上 [shang4] /(bound form) up; upper; above/to go up/\n"
)


def _write_glosses(path: Path, glosses: dict) -> Path:
    path.write_text(json.dumps({"version": 1, "glosses": glosses}), encoding="utf-8")
    return path


@pytest.fixture
def glosses_file(tmp_path, monkeypatch):
    """Point the loader at a temporary learner-gloss file."""
    path = tmp_path / "learner_glosses.json"
    _write_glosses(path, {})
    monkeypatch.setattr(learner_glosses, "LEARNER_GLOSSES_FILE", path)
    return path


@pytest.fixture
def saved_dicts(swap_dictionaries):
    """The shared dictionaries get their contents back after the test."""
    swap_dictionaries()


def _main(entry):
    return next(r for r in entry["readings"] if r["is_main"])


def test_shipped_file_is_well_formed():
    data = json.loads(learner_glosses.LEARNER_GLOSSES_FILE.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert isinstance(data["glosses"], dict)
    for word, item in data["glosses"].items():
        assert item.get("pinyin") and item.get("gloss"), word


def test_gloss_replaces_headline_only(glosses_file):
    _write_glosses(glosses_file, {"太": {"pinyin": "tài", "gloss": "too; very"}})
    parsed = cedict_loader._parse_text(CEDICT)
    tai = parsed["太"]
    assert tai["meaning"] == "too; very"
    assert _main(tai)["primary"] == "too; very"
    # CC-CEDICT senses stay, the gloss is not added to them.
    assert tai["meanings"] == ["highest", "greatest", "too (much)", "very", "extremely"]
    assert tai["pinyin"] == "tài"


def test_gloss_clears_register_tags_of_replaced_sense(glosses_file):
    before = cedict_loader._parse_text(CEDICT)["上"]
    assert before["meaning_tags"], "fixture: the CC-CEDICT headline carries a tag"
    _write_glosses(glosses_file, {"上": {"pinyin": "shàng", "gloss": "up; above; on"}})
    after = cedict_loader._parse_text(CEDICT)["上"]
    assert after["meaning"] == "up; above; on"
    assert after["meaning_tags"] == []
    assert after["meanings"] == before["meanings"]


def test_other_readings_stay_intact(glosses_file):
    before = cedict_loader._parse_text(CEDICT)["好"]
    main_pinyin = before["pinyin"]
    _write_glosses(glosses_file, {"好": {"pinyin": main_pinyin, "gloss": "good; nice"}})
    after = cedict_loader._parse_text(CEDICT)["好"]
    assert after["meaning"] == "good; nice"
    others_before = [r for r in before["readings"] if not r["is_main"]]
    others_after = [r for r in after["readings"] if not r["is_main"]]
    assert others_after == others_before
    assert [r["pinyin"] for r in after["readings"]] == [r["pinyin"] for r in before["readings"]]


def test_pinyin_mismatch_is_skipped_with_warning(glosses_file, caplog):
    before = cedict_loader._parse_text(CEDICT)["教"]
    other = next(r["pinyin"] for r in before["readings"] if not r["is_main"])
    _write_glosses(glosses_file, {"教": {"pinyin": other, "gloss": "religion"}})
    with caplog.at_level(logging.WARNING, logger="app.services.learner_glosses"):
        after = cedict_loader._parse_text(CEDICT)["教"]
    assert after["meaning"] == before["meaning"]
    assert after["readings"] == before["readings"]
    assert any("教" in r.getMessage() and "skipped" in r.getMessage() for r in caplog.records)


def test_pinyin_spacing_and_case_do_not_matter():
    assert learner_glosses.matches_reading("Dōng xi", "dōng xi")
    assert learner_glosses.matches_reading("dōngxi", "dōng xi") is False  # needs syllables
    assert learner_glosses.matches_reading("dōng xi", "dōng xī") is False


def test_entries_without_gloss_or_pinyin_are_ignored(tmp_path):
    path = _write_glosses(
        tmp_path / "g.json",
        {"太": {"pinyin": "tài", "gloss": " "}, "好": {"gloss": "good"}, "教": "to teach"},
    )
    assert learner_glosses.load_learner_glosses(path) == {}
    assert learner_glosses.load_learner_glosses(tmp_path / "missing.json") == {}
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert learner_glosses.load_learner_glosses(tmp_path / "broken.json") == {}


def test_hsk_only_word_gets_gloss(glosses_file, saved_dicts):
    _write_glosses(
        glosses_file, {"车上": {"pinyin": "chē shàng", "gloss": "on the bus; in the car"}}
    )
    state.cedict_vocab.clear()
    state.hsk_vocab.clear()
    state.hsk_vocab["车上"] = {"pinyin": "chē shàng", "meaning": "Car", "meanings": ["Car"]}
    cedict_loader._merge_into_hsk_vocab()
    assert state.hsk_vocab["车上"]["meaning"] == "on the bus; in the car"
    assert state.hsk_vocab["车上"]["meanings"] == ["Car"]


def test_hsk_only_word_with_broken_list_pinyin_is_fixed(glosses_file, saved_dicts):
    _write_glosses(
        glosses_file,
        {
            "不一会儿": {
                "pinyin": "bù yī huìr",
                "gloss": "soon; in a moment",
                "fixes_hsk_pinyin": True,
            },
            "车上": {"pinyin": "chē xià", "gloss": "not applied"},
        },
    )
    state.cedict_vocab.clear()
    state.hsk_vocab.clear()
    state.hsk_vocab["不一会儿"] = {"pinyin": "bù yīhuǐr5", "meaning": "Take a short while"}
    state.hsk_vocab["车上"] = {"pinyin": "chē shàng", "meaning": "Car"}
    cedict_loader._merge_into_hsk_vocab()
    assert state.hsk_vocab["不一会儿"]["pinyin"] == "bù yī huìr"
    assert state.hsk_vocab["不一会儿"]["meanings"] == ["soon", "in a moment"]
    # Without the flag a pinyin mismatch still skips the gloss.
    assert state.hsk_vocab["车上"]["meaning"] == "Car"


def test_merge_carries_gloss_into_hsk_vocab(glosses_file, saved_dicts):
    _write_glosses(glosses_file, {"太": {"pinyin": "tài", "gloss": "too; very"}})
    state.hsk_vocab.clear()
    state.hsk_vocab["太"] = {"pinyin": "tài", "meaning": "highest", "meanings": ["highest"]}
    state.cedict_vocab.clear()
    state.cedict_vocab.update(cedict_loader._parse_text(CEDICT))
    cedict_loader._merge_into_hsk_vocab()
    assert state.hsk_vocab["太"]["meaning"] == "too; very"
    assert "highest" in state.hsk_vocab["太"]["meanings"]


def test_app_pipeline_applies_learner_glosses(glosses_file, saved_dicts):
    """The pinned-data load (startup, gloss_audit, the golden test) runs
    the learner layer, so golden headlines are checked after it."""
    from app.services.word_info import lookup_pinyin_meaning

    _write_glosses(glosses_file, {"太": {"pinyin": "tài", "gloss": "too; very"}})
    dict_data.load_pinned_dictionaries()
    assert lookup_pinyin_meaning("太") == ("tài", "too; very")
    assert "highest" in state.hsk_vocab["太"]["meanings"]


def test_dict_version_changes_with_learner_glosses(tmp_path, monkeypatch):
    for name in dict_data._RULE_FILES:
        src = dict_data.APP_DATA_DIR / name
        if src.exists():
            shutil.copy(src, tmp_path / name)
    monkeypatch.setattr(dict_data, "APP_DATA_DIR", tmp_path)
    monkeypatch.setitem(dict_data.loaded_sources, "hsk", "a" * 64)
    monkeypatch.setitem(dict_data.loaded_sources, "cedict", "b" * 64)
    assert "learner_glosses.json" in dict_data._RULE_FILES
    v1 = dict_data.dict_version()
    _write_glosses(tmp_path / "learner_glosses.json", {"太": {"pinyin": "tài", "gloss": "too"}})
    v2 = dict_data.dict_version()
    assert v2 != v1
    _write_glosses(tmp_path / "learner_glosses.json", {"太": {"pinyin": "tài", "gloss": "very"}})
    assert dict_data.dict_version() not in (v1, v2)


# ---- tools -----------------------------------------------------------------


@pytest.fixture(scope="module")
def tools():
    tools_dir = str(Path(__file__).resolve().parent.parent / "tools")
    sys.path.insert(0, tools_dir)
    try:
        yield (
            importlib.import_module("check_learner_glosses"),
            importlib.import_module("export_gloss_candidates"),
        )
    finally:
        sys.path.remove(tools_dir)


@pytest.fixture
def checker(tools):
    return tools[0]


@pytest.fixture
def ctx(checker):
    return checker.Context(
        hsk_words={"太", "教", "话", "一"},
        main_pinyin={"太": "tài", "教": "jiāo", "话": "huà", "一": "yī"},
        senses={
            "太": ["highest", "greatest", "too (much)", "very", "extremely"],
            "教": ["to teach; to instruct"],
            "话": ["dialect", "language", "spoken words; speech; talk; words"],
            "一": ["one", "single; a (article)"],
        },
        hsk_english={
            "太": "highest; greatest; too (much)",
            "教": "to teach",
            "话": "",
            "一": "one",
        },
    )


def _check(checker, ctx, word, pinyin, gloss, **extra):
    return checker.check_entry(word, {"pinyin": pinyin, "gloss": gloss, **extra}, ctx)


def test_checker_accepts_good_entries(checker, ctx):
    for word, pinyin, gloss in [
        ("太", "tài", "too; very"),
        ("教", "jiāo", "to teach"),
        ("话", "huà", "words; speech"),
        ("一", "yī", "one"),
    ]:
        res = _check(checker, ctx, word, pinyin, gloss)
        assert res.errors == [] and res.flags == [], (word, res)


@pytest.mark.parametrize(
    "word,pinyin,gloss,error",
    [
        ("猫", "māo", "cat", "not an HSK word"),
        ("太", "tai4", "too", "not tone-marked"),
        ("太", "", "too", "not tone-marked"),
        ("教", "jiào", "to teach", "not the main reading"),
        ("太", "tài", "", "empty gloss"),
        ("太", "tài", "too much; " * 5, "longer than 40"),
        ("太", "tài", "(bound form) too", "tag or parenthetical"),
        ("太", "tài", "see 太太", "Chinese characters"),
        ("太", "tài", "variant of too", "pointer"),
        ("太", "tài", "Highest", "known-bad"),
    ],
)
def test_checker_hard_failures(checker, ctx, word, pinyin, gloss, error):
    res = _check(checker, ctx, word, pinyin, gloss)
    assert any(error in e for e in res.errors), res.errors


def test_checker_allows_quoted_chinese(checker, ctx):
    res = _check(checker, ctx, "太", "tài", "too (as in '太好了')")
    assert not any("Chinese" in e for e in res.errors)


def test_checker_allows_grammar_parenthetical(checker, ctx):
    res = _check(checker, ctx, "太", "tài", "(degree adverb particle); too")
    assert not any("parenthetical" in e for e in res.errors)


def test_checker_flags_unsupported_gloss(checker, ctx):
    res = _check(checker, ctx, "太", "tài", "fat; big")
    assert res.errors == []
    assert res.flags == ["no sense support"]
    # Inflected forms count as support: teaching ~ teach.
    assert _check(checker, ctx, "教", "jiāo", "teaching").flags == []


def test_checker_flags_low_confidence(checker, ctx):
    assert _check(checker, ctx, "太", "tài", "too", confidence=0.4).flags == [
        "low confidence (0.4)"
    ]
    assert _check(checker, ctx, "太", "tài", "too", confidence="low").flags == ["low confidence"]
    assert _check(checker, ctx, "太", "tài", "too", confidence=0.9).flags == []


def test_checker_reads_both_shapes_and_flags_duplicates(checker, ctx, tmp_path):
    listed = tmp_path / "written.json"
    listed.write_text(
        json.dumps(
            [
                {"word": "太", "pinyin": "tài", "gloss": "too"},
                {"word": "太", "pinyin": "tài", "gloss": "very"},
            ]
        ),
        encoding="utf-8",
    )
    results = checker.check_entries(checker.read_entries(listed), ctx)
    assert results[0].errors == []
    assert results[1].errors == ["duplicate entry"]
    report = checker.summarize(results)
    assert (report["total"], report["ok"], report["failed"]) == (2, 1, 1)

    shipped = _write_glosses(tmp_path / "g.json", {"教": {"pinyin": "jiāo", "gloss": "to teach"}})
    assert checker.read_entries(shipped) == [("教", {"pinyin": "jiāo", "gloss": "to teach"})]


def test_stemmer_meets_inflections(checker):
    assert checker.content_words("to teach; teaches; teaching") == {"teach"}
    assert checker.content_words("cars") == checker.content_words("car")
    assert checker.content_words("stopped") == checker.content_words("to stop")
    assert checker.content_words("a book of the sb") == {"book"}


# ---- export tool -------------------------------------------------------------


def test_parse_levels(tools):
    export = tools[1]
    assert export.parse_levels("1-4") == [1, 2, 3, 4]
    assert export.parse_levels("1,3") == [1, 3]
    with pytest.raises(ValueError):
        export.parse_levels("")


def test_examples_prefer_short_easy_sentences(tools):
    export = tools[1]
    sentences = [
        {"text": "老师今天在学校里教我们写很多很多很多很多很多很多很多很多很多很多很多很多很多很多很多很多的汉字。", "tokens": frozenset({"教"}), "level": 1},
        {"text": "他教中文。", "tokens": frozenset({"他", "教", "中文"}), "level": 3},
        {"text": "她教我。", "tokens": frozenset({"她", "教", "我"}), "level": 1},
        {"text": "宗教很多。", "tokens": frozenset({"宗教", "很", "多"}), "level": 1},
    ]  # fmt: skip
    assert export.examples_for("教", sentences) == ["她教我。", "他教中文。"]
    # Multi-character words also match inside a longer stored token.
    assert export.examples_for("宗教", sentences[:3]) == []
    assert export.examples_for("中文", sentences) == ["他教中文。"]


def test_library_sentences_are_split_on_tokens(tools, tmp_path):
    export = tools[1]
    text = {
        "hsk_level": 2,
        "text": "我去。你来！",
        "analyzed": {"words": [{"text": t} for t in ["我", "去", "。", "你", "来", "！"]]},
    }
    (tmp_path / "a.json").write_text(json.dumps(text, ensure_ascii=False), encoding="utf-8")
    sentences = export.load_library_sentences(tmp_path)
    assert [s["text"] for s in sentences] == ["我去。", "你来！"]
    assert "来" in sentences[1]["tokens"]
