from rag.chunker import chunk_document
from rag.types import ParsedDoc


def test_chunks_short_doc_into_one_chunk():
    parsed = ParsedDoc(doc_id="abc", text="A short document.",
                       page_texts=["A short document."], metadata={})
    chunks = chunk_document(parsed, source="localfs", account="default",
                            source_url="file:///x", chunk_size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0].text == "A short document."
    assert chunks[0].chunk_idx == 0
    assert chunks[0].chunk_id == "localfs:default:abc:00000"
    assert chunks[0].page_range == (1, 1)


def test_chunks_long_doc_into_many():
    text = "Sentence A. " * 200  # ~2400 chars, should split into multiple chunks
    parsed = ParsedDoc(doc_id="abc", text=text, page_texts=[text], metadata={})
    chunks = chunk_document(parsed, source="localfs", account="default",
                            source_url="file:///x", chunk_size=200, overlap=20)
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c.chunk_idx == i
        assert c.chunk_id == f"localfs:default:abc:{i:05d}"


def test_chunks_preserves_page_range_for_pdf():
    pages = ["Page one content.", "Page two content.", "Page three content."]
    parsed = ParsedDoc(doc_id="abc", text="\n\n".join(pages), page_texts=pages, metadata={})
    chunks = chunk_document(parsed, source="localfs", account="default",
                            source_url="file:///x", chunk_size=512, overlap=0)
    assert all(c.page_range is not None for c in chunks)
