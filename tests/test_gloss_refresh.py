"""Stored glosses follow the dictionary: saved texts (and their public share
view) and vocabulary-list words are re-resolved when the dictionary
version changes, while package, glossary and user-edited meanings stay."""

import json

import pytest

from app.auth import require_auth, require_auth_flexible
from app.database import SavedText, User, VocabularyList
from app.services import dict_data
from app.services.gloss_refresh import DICT_VERSION_KEY, refresh_analysis, resolve_token
from app.state import cedict_vocab, hsk_vocab

V1 = "r1-test-v1"
V2 = "r1-test-v2"


def _hsk(pinyin, meaning, level="new-1"):
    return {
        "pinyin": pinyin,
        "meaning": meaning,
        "meanings": [meaning],
        "level": level,
        "level_new": level,
        "level_old": None,
        "frequency": 1,
    }


def _words():
    return [
        {
            "text": "十点",
            "pinyin": "shí diǎn",
            "meaning": "half-witted",
            "meanings": ["half-witted"],
            "is_hsk": True,
            "hsk_level": "new-1",
            "level_new": "new-1",
            "translation_source": "deepl",
        },
        {
            "text": "苹果",
            "pinyin": "píng guǒ",
            "meaning": "old apple sense",
            "meanings": ["old apple sense"],
            "is_hsk": True,
            "hsk_level": "new-1",
            "level_new": "new-1",
            "translation_source": "hsk",
        },
        {
            "text": "一个",
            "pinyin": "yī gè",
            "meaning": "one + individual",
            "meanings": ["one", "individual"],
            "is_hsk": True,
            "hsk_level": "new-1",
            "level_new": "new-1",
            "translation_source": "hsk-chars",
        },
        {
            "text": "道",
            "pinyin": "dào",
            "meaning": "the Way",
            "meanings": ["the Way"],
            "is_hsk": True,
            "translation_source": "package",
            "package_source": "Daodejing",
        },
        {
            "text": "苹果",
            "pinyin": "píng guǒ",
            "meaning": "my apple",
            "meanings": ["my apple"],
            "is_hsk": True,
            "translation_source": "glossary",
            "glossary_source": "Fruit",
        },
        {"text": "。", "is_hsk": False},
        {"text": "\n", "translation_source": "linebreak", "is_hsk": False},
    ]


@pytest.fixture
def dictionaries():
    saved_hsk, saved_cedict = dict(hsk_vocab), dict(cedict_vocab)
    hsk_vocab.clear()
    cedict_vocab.clear()
    hsk_vocab.update(
        {
            "十": _hsk("shí", "ten"),
            "点": _hsk("diǎn", "o'clock"),
            "苹果": _hsk("píng guǒ", "apple"),
            "一": _hsk("yī", "one"),
            "个": _hsk("gè", "individual"),
            "道": _hsk("dào", "road"),
        }
    )
    cedict_vocab.update(
        {"一个": {"pinyin": "yī gè", "meaning": "one; a", "meanings": ["one", "a"]}}
    )
    yield
    hsk_vocab.clear()
    hsk_vocab.update(saved_hsk)
    cedict_vocab.clear()
    cedict_vocab.update(saved_cedict)


@pytest.fixture
def version(monkeypatch):
    current = {"v": V1}
    monkeypatch.setattr(dict_data, "dict_version", lambda: current["v"])
    return current


@pytest.fixture
def env(app_module, version, memory_db, open_client):
    Session = memory_db

    db = Session()
    db.add(User(id=1, username="alice", password_hash="x", invite_quota=0))
    db.add(
        SavedText(
            id=10,
            user_id=1,
            title="Frozen",
            content="十点苹果一个道苹果。",
            analysis_data=json.dumps({"words": _words(), "statistics": {}}),
            share_token="share-me",
        )
    )
    db.add(
        VocabularyList(
            id=5,
            user_id=1,
            name="Lesson",
            list_type="custom",
            sections=json.dumps(
                [
                    {
                        "name": "Main",
                        "words": [
                            {"hanzi": "苹果", "pinyin": "pingguo", "meaning": "old apple sense"},
                            {"hanzi": "一个", "pinyin": "yī gè", "meaning": "mine", "edited": True},
                            {"hanzi": "自定义", "pinyin": "zì dìng yì", "meaning": "custom"},
                        ],
                    }
                ]
            ),
        )
    )
    db.commit()
    db.close()

    c = open_client(Session)
    overrides = app_module.dependency_overrides
    overrides[require_auth_flexible] = overrides[require_auth]
    return c, Session


@pytest.fixture
def client(env, dictionaries):
    # Dictionaries are swapped in after startup, which reloads them.
    return env


def _stored_analysis(Session, text_id=10):
    s = Session()
    try:
        return json.loads(s.get(SavedText, text_id).analysis_data)
    finally:
        s.close()


def _stored_words(Session, list_id=5):
    s = Session()
    try:
        vl = s.get(VocabularyList, list_id)
        return {w["hanzi"]: w for w in json.loads(vl.sections)[0]["words"]}, vl.dict_version
    finally:
        s.close()


# --- saved texts ----------------------------------------------------------


def test_opening_a_saved_text_refreshes_dictionary_and_mt_tokens(client):
    c, Session = client
    r = c.get("/api/texts/10")
    assert r.status_code == 200
    words = r.json()["analysisData"]["words"]

    shidian = words[0]
    assert shidian["meaning"] == ""
    assert shidian["meanings"] == []
    assert shidian["translation_source"] == "parts"
    assert [p["word"] for p in shidian["parts"]] == ["十", "点"]
    assert shidian["parts"][0]["meaning"] == "ten"
    assert shidian["text"] == "十点"  # boundaries stay as stored

    assert words[1]["meaning"] == "apple"
    assert words[1]["translation_source"] == "hsk"
    assert words[2]["meaning"] == "one; a"
    assert words[2]["translation_source"] == "cedict"

    # Package and glossary glosses are the user's / author's choice.
    assert words[3]["meaning"] == "the Way"
    assert words[3]["translation_source"] == "package"
    assert words[4]["meaning"] == "my apple"
    assert words[4]["translation_source"] == "glossary"
    assert words[5]["text"] == "。"
    assert [w["text"] for w in words] == [w["text"] for w in _words()]

    stored = _stored_analysis(Session)
    assert stored[DICT_VERSION_KEY] == V1
    assert stored["words"][0]["meaning"] == ""
    assert stored["words"][1]["meaning"] == "apple"


def test_second_open_does_not_rewrite(client, version):
    c, Session = client
    c.get("/api/texts/10")
    first = _stored_analysis(Session)

    hsk_vocab["苹果"] = _hsk("píng guǒ", "apple (fruit)")
    r = c.get("/api/texts/10")
    assert r.json()["analysisData"]["words"][1]["meaning"] == "apple"
    assert _stored_analysis(Session) == first

    # A new dictionary version refreshes again.
    version["v"] = V2
    r = c.get("/api/texts/10")
    assert r.json()["analysisData"]["words"][1]["meaning"] == "apple (fruit)"
    assert _stored_analysis(Session)[DICT_VERSION_KEY] == V2


def test_no_refresh_while_dictionaries_are_incomplete(client, version):
    c, Session = client
    version["v"] = None
    r = c.get("/api/texts/10")
    assert r.json()["analysisData"]["words"][0]["meaning"] == "half-witted"
    assert DICT_VERSION_KEY not in _stored_analysis(Session)


def test_share_view_is_refreshed(client):
    c, Session = client
    r = c.get("/api/share/share-me")
    assert r.status_code == 200
    words = r.json()["analysisData"]["words"]
    assert words[0]["meaning"] == ""
    assert words[1]["meaning"] == "apple"
    assert words[3]["meaning"] == "the Way"
    assert _stored_analysis(Session)[DICT_VERSION_KEY] == V1


def test_client_cannot_claim_a_dictionary_version(client):
    c, Session = client
    data = {"words": _words(), "statistics": {}, DICT_VERSION_KEY: V1}
    r = c.post("/api/texts/save", json={"content": "十点", "analysis_data": data})
    new_id = r.json()["id"]
    assert DICT_VERSION_KEY not in _stored_analysis(Session, new_id)
    r = c.get(f"/api/texts/{new_id}")
    assert r.json()["analysisData"]["words"][0]["meaning"] == ""

    r = c.patch(f"/api/texts/{new_id}", json={"analysis_data": data})
    assert r.status_code == 200
    assert DICT_VERSION_KEY not in _stored_analysis(Session, new_id)


def test_resolve_token_carries_optional_analyser_fields(dictionaries):
    hsk_vocab["好"] = {
        **_hsk("hǎo", "good"),
        "readings": [
            {"pinyin": "hǎo", "primary": "good", "meanings": ["good"], "is_main": True},
            {"pinyin": "hào", "primary": "to like", "meanings": ["to like"]},
        ],
    }
    readings = resolve_token("好")["readings"]
    assert [r["pinyin"] for r in readings] == ["hǎo", "hào"]
    assert resolve_token("苹果")["readings"] is None

    data = {"words": [{"text": "好", "translation_source": "hsk", "parts": [{"word": "x"}]}]}
    assert refresh_analysis(data, V1)
    assert "parts" not in data["words"][0]
    assert data["words"][0]["readings"][1]["pinyin"] == "hào"
    assert not refresh_analysis(data, V1)


# --- vocabulary lists ------------------------------------------------------


def test_list_detail_refreshes_unedited_words(client):
    c, Session = client
    r = c.get("/api/vocabulary-lists/5")
    words = {w["hanzi"]: w for w in r.json()["sections"][0]["words"]}
    assert words["苹果"]["meaning"] == "apple"
    assert words["苹果"]["pinyin"] == "píng guǒ"
    assert words["一个"]["meaning"] == "mine"  # edited by the user
    assert words["自定义"]["meaning"] == "custom"  # not in the dictionary

    stored, stored_version = _stored_words(Session)
    assert stored["苹果"]["meaning"] == "apple"
    assert stored_version == V1


def test_lists_index_refreshes_and_stores_version(client, version):
    c, Session = client
    c.get("/api/vocabulary-lists")
    assert _stored_words(Session)[1] == V1

    hsk_vocab["苹果"] = _hsk("píng guǒ", "apple (fruit)")
    r = c.get("/api/vocabulary-lists")
    assert r.json()[0]["sections"][0]["words"][0]["meaning"] == "apple"  # same version

    version["v"] = V2
    r = c.get("/api/vocabulary-lists")
    assert r.json()[0]["sections"][0]["words"][0]["meaning"] == "apple (fruit)"
    assert _stored_words(Session)[1] == V2


def test_editing_a_meaning_protects_it(client, version):
    c, Session = client
    r = c.put(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Main", "old_hanzi": "苹果", "word": {"meaning": "my apple"}},
    )
    assert r.status_code == 200
    assert _stored_words(Session)[0]["苹果"]["edited"] is True

    version["v"] = V2
    r = c.get("/api/vocabulary-lists/5")
    words = {w["hanzi"]: w for w in r.json()["sections"][0]["words"]}
    assert words["苹果"]["meaning"] == "my apple"

    # Setting it back to the dictionary meaning lets it follow the dictionary again.
    c.put(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Main", "old_hanzi": "苹果", "word": {"meaning": "apple"}},
    )
    assert "edited" not in _stored_words(Session)[0]["苹果"]


def test_added_words_mark_user_meanings(client):
    c, Session = client
    c.post(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Main", "hanzi": "十", "meaning": "ten"},
    )
    c.post(
        "/api/vocabulary-lists/5/words",
        json={"section_name": "Main", "hanzi": "点", "meaning": "a dot I like"},
    )
    stored = _stored_words(Session)[0]
    assert "edited" not in stored["十"]
    assert stored["点"]["edited"] is True


def test_csv_export_uses_refreshed_meanings(client):
    c, _ = client
    r = c.get("/api/vocabulary-lists/5/export")
    assert r.status_code == 200
    lines = r.text.splitlines()
    assert "苹果;píng guǒ;apple;" in lines
    assert "一个;yī gè;mine;" in lines
