"""
Pre-analyzed package import — schema validation, strict-mode check,
canonical transform shape.
"""

import pytest

from app.schemas import QingduPackage
from app.services.package_import import (
    PackageImportError,
    transform,
    validate,
)


def _minimal_package(**overrides) -> QingduPackage:
    data = {
        "qingdu_package_version": "1",
        "title": "Test",
        "source": "test-llm",
        "text": "你好。",
        "tokens": [
            {"text": "你好", "pinyin": "nǐ hǎo", "meaning": "hello"},
            {"text": "。", "is_punct": True},
        ],
    }
    data.update(overrides)
    return QingduPackage.model_validate(data)


def test_minimal_package_validates():
    validate(_minimal_package())


def test_non_punct_token_missing_pinyin_rejected():
    pkg = _minimal_package(
        text="你好",
        tokens=[{"text": "你好", "meaning": "hello"}],
    )
    with pytest.raises(PackageImportError):
        validate(pkg)


def test_non_punct_token_missing_meaning_rejected():
    pkg = _minimal_package(
        text="你好",
        tokens=[{"text": "你好", "pinyin": "nǐ hǎo"}],
    )
    with pytest.raises(PackageImportError):
        validate(pkg)


def test_strict_mode_rejects_token_text_mismatch():
    # Note: tokens "你" + "好" reconstruct to "你好", but `text` says "你好啊".
    pkg = _minimal_package(
        text="你好啊",
        tokens=[
            {"text": "你", "pinyin": "nǐ", "meaning": "you"},
            {"text": "好", "pinyin": "hǎo", "meaning": "good"},
        ],
    )
    with pytest.raises(PackageImportError, match="strict=false"):
        validate(pkg, strict=True)


def test_non_strict_mode_accepts_mismatch():
    pkg = _minimal_package(
        text="你好啊",
        tokens=[
            {"text": "你", "pinyin": "nǐ", "meaning": "you"},
            {"text": "好", "pinyin": "hǎo", "meaning": "good"},
        ],
    )
    validate(pkg, strict=False)  # should not raise


def test_transform_emits_canonical_shape():
    pkg = _minimal_package()
    out = transform(pkg)
    assert "words" in out
    assert "statistics" in out
    assert "grammar" in out
    assert len(out["words"]) == 2  # 你好 + 。
    first = out["words"][0]
    assert first["text"] == "你好"
    assert first["pinyin"] == "nǐ hǎo"
    assert first["meaning"] == "hello"
    assert first["translation_source"] == "package"
    assert first["package_source"] == "test-llm"


def test_transform_passes_through_punctuation():
    pkg = _minimal_package()
    out = transform(pkg)
    punct = out["words"][1]
    assert punct["text"] == "。"
    assert punct["is_hsk"] is False


def test_transform_preserves_token_notes():
    """The author's contextual `notes` field rides along into the response."""
    pkg = _minimal_package(
        text="道",
        tokens=[
            {
                "text": "道",
                "pinyin": "dào",
                "meaning": "the Way / Tao",
                "notes": "Verb here: to speak of.",
            }
        ],
    )
    out = transform(pkg)
    assert out["words"][0]["notes"] == "Verb here: to speak of."


def test_same_character_can_have_different_meanings():
    """The headline value vs jieba: contextual disambiguation."""
    pkg = _minimal_package(
        text="道可道",
        tokens=[
            {"text": "道", "pinyin": "dào", "meaning": "the Way (noun)"},
            {"text": "可", "pinyin": "kě", "meaning": "can"},
            {"text": "道", "pinyin": "dào", "meaning": "to speak of (verb)"},
        ],
    )
    out = transform(pkg)
    assert out["words"][0]["meaning"] == "the Way (noun)"
    assert out["words"][2]["meaning"] == "to speak of (verb)"


def test_empty_text_rejected():
    pkg = _minimal_package(text="  ", tokens=[{"text": "x", "is_punct": True}])
    with pytest.raises(PackageImportError):
        validate(pkg)


def test_empty_tokens_rejected():
    pkg = _minimal_package(text="你好", tokens=[])
    with pytest.raises(PackageImportError):
        validate(pkg)
