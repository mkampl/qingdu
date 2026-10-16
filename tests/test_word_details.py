"""Measure words and character components (services/word_details)."""

from fastapi.testclient import TestClient

from app.services import word_details


def test_measure_words_come_from_the_shown_reading(app_module):
    with TestClient(app_module):
        assert [c["hanzi"] for c in word_details.classifiers("书")][:2] == ["本", "册"]
        assert word_details.classifiers("桌子")[0] == {"hanzi": "张", "pinyin": "zhāng"}
        assert word_details.classifiers("好") == []


def test_components_split_a_character_into_its_parts(app_module):
    with TestClient(app_module):
        (hao,) = word_details.components("好")
        assert [p["char"] for p in hao["parts"]] == ["女", "子"]
        assert hao["hint"] == "A woman 女 with a son 子"
        assert hao["parts"][0]["definition"].startswith("woman")


def test_sound_and_meaning_parts_are_named(app_module):
    with TestClient(app_module):
        (zhi,) = word_details.components("纸")
        assert zhi["hint"].startswith("纟") and "the sound" in zhi["hint"]


def test_endpoint(app_module):
    with TestClient(app_module) as c:
        r = c.get("/api/vocab/details/休息")
        assert r.status_code == 200
        body = r.json()
        assert [ch["char"] for ch in body["characters"]] == ["休", "息"]
        assert c.get("/api/vocab/details/" + "好" * 13).status_code == 400
