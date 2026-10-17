"""The LLM as first translator (with the text's glossary terms) and as OCR
for photos."""

import asyncio
import io
import json

from PIL import Image

from app.database import VocabularyList
from app.services import image_ocr, translation
from tests.test_grammar_ai import fake_llm  # noqa: F401
from tests.test_user_words import words_client as _words_client

words_client = _words_client


def test_the_llm_translates_first_and_gets_the_glossary_terms(fake_llm):  # noqa: F811
    fake_llm.append("Guarding an aperture serves only to treat illness.")
    out = asyncio.run(
        translation.get_translation_with_source(
            "守窍只能用于治病。", [("守窍", "guarding an aperture")]
        )
    )
    assert out == {
        "translation": "Guarding an aperture serves only to treat illness.",
        "source": "llm",
    }


def test_a_chinese_answer_is_no_translation(fake_llm, monkeypatch):  # noqa: F811
    fake_llm.append("守窍只能用于治病。")

    async def mymemory(*a, **kw):
        return None

    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_TRANSLATE_API_KEY", raising=False)
    monkeypatch.setattr(translation, "_call_translation_api", mymemory)
    assert asyncio.run(translation._llm_translation("守窍只能用于治病。", [])) is None


def test_translate_passes_the_texts_glossary_terms(words_client, monkeypatch):
    s = words_client.session_factory()
    words = [
        {"hanzi": "守窍", "meaning": "guarding an aperture"},
        {"hanzi": "道", "meaning": "Dao"},
    ]
    s.add(
        VocabularyList(
            id=7,
            user_id=1,
            name="Glossar",
            sections=json.dumps([{"name": "A", "words": words}]),
            apply_as_glossary=False,
        )
    )
    s.commit()
    s.close()
    seen = []

    async def fake(text, terms=None):
        seen.append(terms)
        return {"translation": "x", "source": "llm"}

    monkeypatch.setattr("app.routers.translate.get_translation_with_source", fake)
    words_client.post("/api/translate", json={"text": "守窍之道。", "glossary_list_ids": [7]})
    words_client.post("/api/translate", json={"text": "守窍之道？"})  # list not flagged: none
    # Single characters (道) are left out: far more often everyday words.
    assert seen == [[("守窍", "guarding an aperture")], []]


def _photo() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (3000, 1000), (240, 240, 230)).save(out, format="PNG")
    return out.getvalue()


def test_a_photo_is_read_by_the_llm(words_client, fake_llm):  # noqa: F811
    fake_llm.append(
        "```\n上个月开了一家茶馆。\n茶很好喝。\n茶很好喝。\n茶很好喝。\n茶很好喝。\n```"
    )
    r = words_client.post("/api/extract/image", files={"file": ("p.png", _photo(), "image/png")})
    assert r.status_code == 200
    # Fences gone, a looping line kept at most twice.
    assert r.json()["content"] == "上个月开了一家茶馆。\n茶很好喝。\n茶很好喝。"
    assert r.json()["url"] == "scan://p.png"


def test_a_photo_without_chinese_or_no_image_is_refused(words_client, fake_llm):  # noqa: F811
    fake_llm.append("")
    r = words_client.post("/api/extract/image", files={"file": ("p.png", _photo(), "image/png")})
    assert r.status_code == 422
    r = words_client.post(
        "/api/extract/image", files={"file": ("p.png", b"not an image", "image/png")}
    )
    assert r.status_code == 422


def test_photos_are_scaled_down():
    img = Image.open(io.BytesIO(image_ocr.prepare(_photo())))
    assert max(img.size) == image_ocr.MAX_SIDE and img.format == "JPEG"


def test_ocr_is_off_without_an_llm(words_client):
    r = words_client.post("/api/extract/image", files={"file": ("p.png", _photo(), "image/png")})
    assert r.status_code == 503
