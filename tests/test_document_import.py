"""
EPUB / PDF text extraction. We build tiny in-memory fixtures so the tests
stay hermetic — no fixture files on disk.
"""

import io

import pytest
from ebooklib import epub
from pypdf import PdfWriter

from app.services.document_import import (
    DocumentImportError,
    extract_document,
)


def _build_epub_bytes() -> bytes:
    book = epub.EpubBook()
    book.set_identifier("test")
    book.set_title("测试书")
    book.set_language("zh")
    book.add_author("测试作者")
    chapter = epub.EpubHtml(title="Chapter 1", file_name="ch1.xhtml", lang="zh")
    chapter.content = "<html><body><p>这是第一章的内容。</p><p>第二段。</p></body></html>"
    book.add_item(chapter)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    buf = io.BytesIO()
    epub.write_epub(buf, book)
    return buf.getvalue()


def test_extract_epub_returns_text_and_metadata():
    doc = extract_document("test.epub", _build_epub_bytes())
    assert doc.source_kind == "epub"
    assert doc.title == "测试书"
    assert doc.byline == "测试作者"
    assert "第一章" in doc.content
    assert "第二段" in doc.content
    assert doc.char_count == len(doc.content)


def test_unsupported_extension_raises():
    with pytest.raises(DocumentImportError):
        extract_document("notes.txt", b"hello")


def test_empty_pdf_raises_with_hint():
    """A blank PDF (no text) should fail with a message pointing at OCR."""
    writer = PdfWriter()
    # A single blank page — no text content.
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(DocumentImportError) as exc:
        extract_document("scanned.pdf", buf.getvalue())
    assert "scan" in str(exc.value).lower() or "ocr" in str(exc.value).lower()


def test_malformed_pdf_raises():
    with pytest.raises(DocumentImportError):
        extract_document("oops.pdf", b"not a pdf")
