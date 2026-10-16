"""
EPUB / PDF / subtitle text extraction. The output mirrors the trafilatura-extracted
URL shape so the reader can treat all imports uniformly: a single body
string plus optional title and byline.

We deliberately don't OCR scanned PDFs here — that's Phase E3's job
(browser-side tesseract.js). If a PDF has no extractable text we surface
that fact so the SPA can tell the user instead of silently importing an
empty page.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub
from pypdf import PdfReader

# Cap to mirror the URL-extract cap. Users importing a whole novel will hit
# this; we'd rather they chapter-split than we OOM jieba on a 500k-char job.
_MAX_CHARS = 50_000


@dataclass
class ExtractedDocument:
    title: str | None
    byline: str | None
    content: str
    char_count: int
    source_kind: str  # "epub" | "pdf" | "subtitles"


class DocumentImportError(Exception):
    """Raised when a file can't be turned into useful Chinese text."""


def extract_document(filename: str, data: bytes) -> ExtractedDocument:
    """
    Dispatch on extension. Anything not .epub/.pdf raises. EPUB and PDF
    each route through their own extractor.
    """
    lower = filename.lower()
    if lower.endswith(".epub"):
        return _extract_epub(data)
    if lower.endswith(".pdf"):
        return _extract_pdf(data)
    if lower.endswith(SUBTITLE_SUFFIXES):
        return _extract_subtitles(filename, data)
    raise DocumentImportError(
        f"Unsupported file type: {filename!r}. Use .epub, .pdf, .srt, .vtt or .ass."
    )


# --- Subtitles (SRT / WebVTT / ASS) ------------------------------------------

SUBTITLE_SUFFIXES = (".srt", ".vtt", ".ass", ".ssa")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_TIMING_RE = re.compile(r"\d+:\d+[:.,]\d+.*-->")
_TAG_RE = re.compile(r"<[^>]+>|\{[^}]*\}")


def _decode_text(data: bytes) -> str:
    """UTF-8 (with or without BOM) or UTF-16 with BOM, else GB18030, the
    usual encodings of Chinese subtitle files."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _subtitle_lines(text: str, ass: bool) -> list[str]:
    """The spoken lines of a subtitle file, one per cue line."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if ass:
            if not line.startswith("Dialogue:"):
                continue
            # Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
            line = line.split(",", 9)[-1].replace("\\N", "\n").replace("\\n", "\n")
        elif (
            not line
            or line.isdigit()
            or _TIMING_RE.search(line)
            or line.startswith(("WEBVTT", "NOTE", "STYLE", "REGION"))
        ):
            continue
        for part in _TAG_RE.sub("", line).splitlines():
            part = part.strip()
            out.append(part)
    return out


def _extract_subtitles(filename: str, data: bytes) -> ExtractedDocument:
    """Chinese lines of a subtitle file as a text, one line per subtitle
    line. Lines without Chinese (the English half of bilingual subtitles,
    sound cues) are dropped, and so are immediate repeats (subtitles that
    stay on screen across two cues)."""
    text = _decode_text(data)
    lines: list[str] = []
    for line in _subtitle_lines(text, ass=filename.lower().endswith((".ass", ".ssa"))):
        if not _CJK_RE.search(line):
            continue
        if lines and lines[-1] == line:
            continue
        lines.append(line)
    if not lines:
        raise DocumentImportError("No Chinese lines found in these subtitles.")
    content = "\n".join(lines)
    if len(content) > _MAX_CHARS:
        content = content[:_MAX_CHARS].rsplit("\n", 1)[0]
    title = re.sub(r"\.(srt|vtt|ass|ssa)$", "", filename.rsplit("/", 1)[-1], flags=re.I)
    return ExtractedDocument(
        title=title or None,
        byline=None,
        content=content,
        char_count=len(content),
        source_kind="subtitles",
    )


# --- EPUB ------------------------------------------------------------------


def _extract_epub(data: bytes) -> ExtractedDocument:
    try:
        # EbookLib reads from disk; route via BytesIO via the public helper.
        book = epub.read_epub(io.BytesIO(data))
    except Exception as e:
        raise DocumentImportError(f"Couldn't parse EPUB: {e}") from e

    title = _epub_meta_first(book, "title")
    byline = _epub_meta_first(book, "creator")

    chunks: list[str] = []
    total_chars = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        try:
            html = item.get_content().decode("utf-8", errors="replace")
        except Exception:
            continue
        text = _html_to_text(html)
        if not text:
            continue
        chunks.append(text)
        total_chars += len(text)
        if total_chars > _MAX_CHARS:
            break

    content = "\n\n".join(chunks).strip()
    if not content:
        raise DocumentImportError("EPUB contained no readable text.")
    if len(content) > _MAX_CHARS:
        content = content[:_MAX_CHARS]

    return ExtractedDocument(
        title=title,
        byline=byline,
        content=content,
        char_count=len(content),
        source_kind="epub",
    )


def _epub_meta_first(book: epub.EpubBook, name: str) -> str | None:
    items = book.get_metadata("DC", name)
    if not items:
        return None
    value = items[0][0]
    return value.strip() if value else None


_BLOCK_BREAK = re.compile(r"\n{3,}")


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Drop script/style/nav-like noise.
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    # Insert blank lines between block elements so paragraphs survive
    # the .get_text() flattening.
    text = soup.get_text(separator="\n").strip()
    return _BLOCK_BREAK.sub("\n\n", text)


# --- PDF -------------------------------------------------------------------


def _extract_pdf(data: bytes) -> ExtractedDocument:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        raise DocumentImportError(f"Couldn't parse PDF: {e}") from e

    title = None
    byline = None
    meta = getattr(reader, "metadata", None)
    if meta:
        title = (meta.get("/Title") or "").strip() or None
        byline = (meta.get("/Author") or "").strip() or None

    chunks: list[str] = []
    total_chars = 0
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = text.strip()
        if text:
            chunks.append(text)
            total_chars += len(text)
        if total_chars > _MAX_CHARS:
            break

    content = "\n\n".join(chunks).strip()
    if not content:
        raise DocumentImportError(
            "PDF contained no extractable text — it's likely a scanned image. "
            "Use the Scan tool (OCR) instead."
        )
    if len(content) > _MAX_CHARS:
        content = content[:_MAX_CHARS]

    return ExtractedDocument(
        title=title,
        byline=byline,
        content=content,
        char_count=len(content),
        source_kind="pdf",
    )


__all__ = ["DocumentImportError", "ExtractedDocument", "extract_document"]
