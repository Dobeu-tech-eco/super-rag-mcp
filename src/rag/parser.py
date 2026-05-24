"""Document parser with PDF text extraction + OCR fallback + DOCX + TXT."""
from __future__ import annotations
from io import BytesIO
from typing import Literal
import fitz  # pymupdf
from docx import Document as DocxDocument
from rag.types import ParsedDoc, RawDoc

OcrStrategy = Literal["auto_detect", "always", "never"]

_TEXT_MIMES = {"text/plain", "text/markdown"}
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def parse(raw: RawDoc, ocr_strategy: OcrStrategy = "auto_detect",
          min_chars_per_page: int = 100) -> ParsedDoc:
    if raw.mime == "application/pdf":
        return _parse_pdf(raw, ocr_strategy, min_chars_per_page)
    if raw.mime == _DOCX_MIME:
        return _parse_docx(raw)
    if raw.mime in _TEXT_MIMES:
        return _parse_text(raw)
    raise ValueError(f"unsupported MIME for parser: {raw.mime}")


def _parse_pdf(raw: RawDoc, ocr_strategy: OcrStrategy, min_chars_per_page: int) -> ParsedDoc:
    doc = fitz.open(stream=raw.content, filetype="pdf")
    try:
        page_texts: list[str] = []
        for page in doc:
            page_texts.append(page.get_text() or "")
        total_chars = sum(len(t) for t in page_texts)
        avg = total_chars / max(1, len(page_texts))
        used_ocr = False
        if ocr_strategy == "always" or (ocr_strategy == "auto_detect" and avg < min_chars_per_page):
            page_texts = _ocr_pdf(raw.content)
            used_ocr = True
        return ParsedDoc(
            doc_id=raw.doc_id,
            text="\n\n".join(page_texts),
            page_texts=page_texts,
            metadata={"used_ocr": used_ocr, "page_count": len(page_texts)},
        )
    finally:
        doc.close()


def _ocr_pdf(content: bytes) -> list[str]:
    # Lazy import — OCR deps are heavy and not always available.
    from pdf2image import convert_from_bytes
    import pytesseract
    images = convert_from_bytes(content, dpi=200)
    texts: list[str] = []
    for img in images:
        texts.append(pytesseract.image_to_string(img) or "")
    return texts


def _parse_docx(raw: RawDoc) -> ParsedDoc:
    doc = DocxDocument(BytesIO(raw.content))
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    text = "\n".join(paragraphs)
    return ParsedDoc(
        doc_id=raw.doc_id,
        text=text,
        page_texts=[text],  # DOCX has no native pages
        metadata={"used_ocr": False, "paragraph_count": len(paragraphs)},
    )


def _parse_text(raw: RawDoc) -> ParsedDoc:
    text = raw.content.decode("utf-8", errors="replace")
    return ParsedDoc(
        doc_id=raw.doc_id,
        text=text,
        page_texts=[text],
        metadata={"used_ocr": False},
    )
