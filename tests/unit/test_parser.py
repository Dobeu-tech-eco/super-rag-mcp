from datetime import datetime
from pathlib import Path
import pytest
from rag.parser import parse
from rag.types import RawDoc


def _raw(filename: str, content: bytes, mime: str) -> RawDoc:
    return RawDoc(
        doc_id=filename, source="localfs", account="default",
        source_url=f"file:///{filename}", mime=mime,
        content=content, filename=filename, last_modified=datetime(2026, 5, 23),
    )


def test_parse_text_pdf(fixtures_dir: Path):
    data = (fixtures_dir / "text.pdf").read_bytes()
    parsed = parse(_raw("text.pdf", data, "application/pdf"), ocr_strategy="auto_detect")
    assert "Hello text PDF" in parsed.text
    assert len(parsed.page_texts) >= 1
    assert parsed.metadata["used_ocr"] is False


def test_parse_docx(fixtures_dir: Path):
    data = (fixtures_dir / "sample.docx").read_bytes()
    parsed = parse(_raw("sample.docx", data,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                   ocr_strategy="auto_detect")
    assert "Hello DOCX" in parsed.text


def test_parse_txt(fixtures_dir: Path):
    data = (fixtures_dir / "sample.txt").read_bytes()
    parsed = parse(_raw("sample.txt", data, "text/plain"), ocr_strategy="auto_detect")
    assert "plain text fixture" in parsed.text


def test_parse_unsupported_mime_raises():
    with pytest.raises(ValueError, match="unsupported"):
        parse(_raw("x.bin", b"\x00\x01", "application/octet-stream"),
              ocr_strategy="auto_detect")


@pytest.mark.skipif(
    not (Path(__file__).parent.parent / "fixtures" / "scanned.pdf").exists(),
    reason="scanned.pdf fixture not provided",
)
def test_parse_scanned_pdf_uses_ocr(fixtures_dir: Path):
    data = (fixtures_dir / "scanned.pdf").read_bytes()
    parsed = parse(_raw("scanned.pdf", data, "application/pdf"), ocr_strategy="auto_detect")
    assert parsed.metadata["used_ocr"] is True
    assert len(parsed.text) > 0
