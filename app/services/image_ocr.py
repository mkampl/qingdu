"""Chinese text from a photo, read by the server's LLM (a vision model).

The photo is turned upright (EXIF), scaled down to MAX_SIDE and sent as
JPEG; the model copies the Chinese text line by line. Vision models can
make up text on an empty or unreadable image, so an answer without
Chinese is refused and runs of the same line are cut. The text is only
a draft: the import preview shows it for checking before it is read.
"""

from __future__ import annotations

import asyncio
import base64
import io
import re

from PIL import Image, ImageOps, UnidentifiedImageError

from app.services import llm

FEATURE = "ocr"
MAX_SIDE = 1600
MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 150
_CJK = re.compile(r"[㐀-鿿]")
_FENCE = re.compile(r"^```\w*\s*|\s*```$")

PROMPT = """Copy the Chinese text in this image exactly, line by line, in reading order (vertical
text: columns right to left). Keep every character as written, simplified or traditional, with
its punctuation. Leave out page numbers and running heads. Do not translate, explain or add
anything. If the image has no Chinese text, answer with an empty reply."""


class OcrError(ValueError):
    """The image could not be read."""


def prepare(data: bytes) -> bytes:
    """The photo upright, at most MAX_SIDE pixels on its long side, as JPEG."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except (UnidentifiedImageError, OSError) as e:
        raise OcrError("That file is not an image we can read.") from e
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue()


def clean(text: str) -> str:
    """The model's answer as plain lines; a line repeated over and over
    (a vision model looping) is kept at most twice in a row."""
    text = _FENCE.sub("", (text or "").strip())
    lines, last, repeats = [], None, 0
    for line in (x.strip() for x in text.splitlines()):
        if line and line == last:
            repeats += 1
            if repeats >= 2:
                continue
        else:
            repeats = 0
        lines.append(line)
        last = line
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


async def read_text(data: bytes) -> str:
    jpeg = await asyncio.to_thread(prepare, data)
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    reply = await llm.chat(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        ],
        max_tokens=3000,
        temperature=0,
        timeout=TIMEOUT,
    )
    text = clean(str(reply or ""))
    if len(_CJK.findall(text)) < 2:
        raise OcrError("No Chinese text found in that image. Try a sharper, closer photo.")
    return text


__all__ = ["FEATURE", "MAX_BYTES", "OcrError", "clean", "prepare", "read_text"]
