"""
Display-script helpers — to_user_script / to_canonical / the analysis
+ vocab walkers used by /api/texts and /api/vocabulary-lists.
"""

from app.database import User
from app.services import script


def _user(pref: str) -> User:
    u = User()
    u.display_script = pref
    return u


def test_to_user_script_auto_is_noop():
    assert script.to_user_script("学习", _user("auto")) == "学习"
    # Even with traditional input we pass through on auto.
    assert script.to_user_script("學習", _user("auto")) == "學習"


def test_to_user_script_simp_normalises_trad():
    assert script.to_user_script("學習", _user("simp")) == "学习"


def test_to_user_script_trad_converts_simp():
    assert script.to_user_script("学习", _user("trad")) == "學習"


def test_to_canonical_anonymous_passes_through():
    # No user → 'auto' default → no conversion.
    assert script.to_canonical("學習", None) == "學習"


def test_to_canonical_for_trad_user_normalises_for_storage():
    # A trad user posting "earth" back to the server should land in simp.
    assert script.to_canonical("學習", _user("trad")) == "学习"


def test_convert_analysis_data_walks_words_and_sentences():
    data = {
        "words": [
            {"text": "学习", "pinyin": "xué xí", "meaning": "to study"},
            {"text": "我", "pinyin": "wǒ", "meaning": "I"},
        ],
        "grammar": {
            "sentences": [
                {"text": "我学习。", "words": ["我", "学习"]},
            ]
        },
    }
    out = script.convert_analysis_data(data, _user("trad"))
    assert out["words"][0]["text"] == "學習"
    assert out["words"][1]["text"] == "我"
    assert out["grammar"]["sentences"][0]["text"] == "我學習。"
    # Pinyin / meaning untouched.
    assert out["words"][0]["pinyin"] == "xué xí"
    assert out["words"][0]["meaning"] == "to study"


def test_convert_analysis_data_auto_skips_walk():
    data = {"words": [{"text": "学习", "pinyin": "xué xí"}]}
    out = script.convert_analysis_data(data, _user("auto"))
    assert out["words"][0]["text"] == "学习"


def test_convert_vocab_sections_walks_hanzi_and_traditional():
    sections = [
        {
            "name": "Lesson 1",
            "words": [
                {
                    "hanzi": "学习",
                    "traditional": "學習",
                    "pinyin": "xué xí",
                    "meaning": "to study",
                },
                {"hanzi": "好", "pinyin": "hǎo", "meaning": "good"},
            ],
        }
    ]
    out = script.convert_vocab_sections(sections, _user("trad"))
    # hanzi flipped, traditional already trad stays trad.
    assert out[0]["words"][0]["hanzi"] == "學習"
    assert out[0]["words"][0]["traditional"] == "學習"
    # 好 has no trad variant; conversion idempotent.
    assert out[0]["words"][1]["hanzi"] == "好"
    # Section name + pinyin + meaning untouched.
    assert out[0]["name"] == "Lesson 1"
    assert out[0]["words"][0]["pinyin"] == "xué xí"
    assert out[0]["words"][0]["meaning"] == "to study"


def test_convert_vocab_sections_handles_empty_and_none():
    assert script.convert_vocab_sections(None, _user("trad")) is None
    assert script.convert_vocab_sections([], _user("trad")) == []
