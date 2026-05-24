"""
Traditional ⇄ Simplified Chinese conversion via OpenCC.

The rest of the app (HSK vocab, jieba, popovers) works against Simplified —
this endpoint just lets the user paste-then-flip rather than juggling a
separate converter tab.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from opencc import OpenCC
from pydantic import BaseModel

router = APIRouter(tags=["Convert"])


# Direction-keyed converter cache. OpenCC instantiation reads a JSON config
# from disk; we only want to do it once per direction per process.
_CONVERTERS: dict[str, OpenCC] = {}


def _converter(direction: str) -> OpenCC:
    if direction not in _CONVERTERS:
        _CONVERTERS[direction] = OpenCC(direction)
    return _CONVERTERS[direction]


# Range of Traditional-only / Variant CJK characters we sample on auto-detect.
# Anything in the CJK Compatibility Ideographs block or above the basic CJK
# range is a strong "this is Traditional" signal. Far from perfect — many
# Traditional characters share codepoints with Simplified — but combined
# with a round-trip check below it's enough to surface a suggestion to the
# user.
_TRADITIONAL_INDICATOR_CHARS = set(
    "繁體華個來時動學東說國這個樣這種會應該過導為門題該專業點數"
    "電當會與內為對於現經發產業務開發學習產業變數電腦東西華語"
)


class ConvertRequest(BaseModel):
    text: str
    direction: Literal["s2t", "t2s"]


class DetectRequest(BaseModel):
    text: str


@router.post("/api/convert")
async def convert_script(payload: ConvertRequest) -> dict:
    text = payload.text
    if not text:
        return {"converted": "", "direction": payload.direction}
    try:
        converted = _converter(payload.direction).convert(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e!s}") from e
    return {"converted": converted, "direction": payload.direction}


@router.post("/api/convert/detect")
async def detect_script(payload: DetectRequest) -> dict:
    """
    Heuristic: does this text look Traditional? Sample the first ~400 CJK
    characters and check what fraction survive a round-trip through t2s.
    If lots of characters change shape, the input was Traditional.

    Returns {script: "simplified" | "traditional" | "unknown", confidence: float}.
    """
    text = payload.text
    if not text:
        return {"script": "unknown", "confidence": 0.0}

    sample = []
    for ch in text:
        if "一" <= ch <= "鿿":
            sample.append(ch)
        if len(sample) >= 400:
            break
    if not sample:
        return {"script": "unknown", "confidence": 0.0}

    sample_str = "".join(sample)
    simplified = _converter("t2s").convert(sample_str)
    # Count chars that changed under t2s — those are Traditional-only.
    changed = sum(1 for a, b in zip(sample_str, simplified, strict=False) if a != b)
    indicator_hits = sum(1 for ch in sample if ch in _TRADITIONAL_INDICATOR_CHARS)
    confidence = min(1.0, (changed / len(sample)) + (indicator_hits / 50))
    if confidence >= 0.05:
        return {"script": "traditional", "confidence": round(confidence, 3)}
    return {"script": "simplified", "confidence": round(1.0 - confidence, 3)}
