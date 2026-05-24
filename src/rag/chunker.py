"""Sentence-aware chunker that preserves source-page mapping."""
from __future__ import annotations
from llama_index.core.node_parser import SentenceSplitter
from rag.types import Chunk, ParsedDoc


def chunk_document(parsed: ParsedDoc, source: str, account: str, source_url: str,
                   chunk_size: int = 512, overlap: int = 64) -> list[Chunk]:
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    text_chunks = splitter.split_text(parsed.text)

    # Build a character-to-page index for page-range derivation.
    page_breaks: list[tuple[int, int]] = []  # (char_end_exclusive, page_num)
    cursor = 0
    for i, page in enumerate(parsed.page_texts, start=1):
        cursor += len(page) + 2  # "\n\n" join in parse_pdf
        page_breaks.append((cursor, i))

    def page_range_for(chunk_text: str, search_from: int) -> tuple[int, int] | None:
        if not page_breaks:
            return None
        start = parsed.text.find(chunk_text, search_from)
        if start < 0:
            start = search_from
        end = start + len(chunk_text)
        first = next((p for ce, p in page_breaks if ce > start), page_breaks[-1][1])
        last = next((p for ce, p in page_breaks if ce >= end), page_breaks[-1][1])
        return (first, last)

    chunks: list[Chunk] = []
    cursor = 0
    for idx, text in enumerate(text_chunks):
        pr = page_range_for(text, cursor)
        if pr is None:
            pr = (1, 1)
        chunks.append(Chunk(
            chunk_id=f"{source}:{account}:{parsed.doc_id}:{idx:05d}",
            doc_id=parsed.doc_id,
            chunk_idx=idx,
            text=text,
            page_range=pr,
            source_url=source_url,
        ))
        cursor += max(1, len(text) - overlap)
    return chunks
