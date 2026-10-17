"""Reader/review preferences on the account (services/ui_settings)."""

from app.services import ui_settings
from tests.test_user_words import words_client as _words_client

words_client = _words_client


def test_only_known_keys_with_valid_values_are_kept():
    assert ui_settings.clean(
        {
            "pinyinMode": "off",
            "colorMode": "rainbow",
            "showLegend": True,
            "reviewSingleMode": "yes",
            "autoGradeDelayMs": 2500,
            "theme": "dark",
            "hskVersion": {"x": 1},
        }
    ) == {"pinyinMode": "off", "showLegend": True, "autoGradeDelayMs": 2500}
    assert ui_settings.clean({"autoGradeDelayMs": True}) == {}
    assert ui_settings.clean({"autoGradeDelayMs": 99_999}) == {}


def test_updates_merge_key_by_key(words_client):
    me = words_client.get("/api/auth/me").json()["user"]
    assert me["ui_settings"] is None
    r = words_client.patch(
        "/api/auth/me/settings", json={"ui_settings": {"pinyinMode": "off", "colorMode": "hsk"}}
    )
    assert r.status_code == 200
    assert r.json()["ui_settings"] == {"pinyinMode": "off", "colorMode": "hsk"}
    words_client.patch("/api/auth/me/settings", json={"ui_settings": {"colorMode": "progress"}})
    me = words_client.get("/api/auth/me").json()["user"]
    assert me["ui_settings"] == {"pinyinMode": "off", "colorMode": "progress"}
