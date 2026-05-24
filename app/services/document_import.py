"""
EPUB / PDF text extraction. The output mirrors the trafilatura-extracted
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
    source_kind: str  # "epub" | "pdf"


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
    raise DocumentImportError(f"Unsupported file type: {filename!r}. Use .epub or .pdf.")


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
