from datetime import datetime
from pathlib import Path
import pytest
from rag.metadata import MetadataStore
from rag.types import ChangeEvent, Chunk


@pytest.fixture
def store(tmp_path: Path) -> MetadataStore:
    return MetadataStore(tmp_path / "meta.sqlite")


def test_upsert_and_get_document(store: MetadataStore):
    event = ChangeEvent(
        source="localfs", account="default", doc_id="abc",
        operation="upsert", source_url="file:///tmp/x.pdf",
        last_modified=datetime(2026, 5, 23, 0, 0), size_bytes=1234, mime="application/pdf",
    )
    store.upsert_document(event, content_hash="deadbeef")
    doc = store.get_document("localfs", "default", "abc")
    assert doc is not None
    assert doc["content_hash"] == "deadbeef"
    assert doc["status"] == "indexed"


def test_mark_failed_and_deleted(store: MetadataStore):
    event = ChangeEvent(
        source="localfs", account="default", doc_id="abc",
        operation="upsert", source_url="file:///tmp/x.pdf",
        last_modified=datetime(2026, 5, 23), size_bytes=1, mime="text/plain",
    )
    store.upsert_document(event, content_hash="h")
    store.mark_failed("localfs", "default", "abc", reason="bad pdf")
    assert store.get_document("localfs", "default", "abc")["status"] == "failed"
    store.mark_deleted("localfs", "default", "abc")
    assert store.get_document("localfs", "default", "abc")["status"] == "deleted"


def test_chunks_roundtrip(store: MetadataStore):
    event = ChangeEvent(source="localfs", account="default", doc_id="abc",
                        operation="upsert", source_url="file:///x", last_modified=datetime(2026, 5, 23))
    store.upsert_document(event, content_hash="h")
    chunks = [
        Chunk(chunk_id="localfs:default:abc:00000", doc_id="abc", chunk_idx=0,
              text="hello", page_range=(1, 1), source_url="file:///x"),
        Chunk(chunk_id="localfs:default:abc:00001", doc_id="abc", chunk_idx=1,
              text="world", page_range=(1, 1), source_url="file:///x"),
    ]
    store.upsert_chunks(chunks)
    hydrated = store.hydrate_chunks(["localfs:default:abc:00001", "localfs:default:abc:00000"])
    assert {c["chunk_id"] for c in hydrated} == {c.chunk_id for c in chunks}


def test_run_log(store: MetadataStore):
    rid = store.start_run()
    store.finish_run(rid, status="success", docs_processed=10, chunks_indexed=42)
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["chunks_indexed"] == 42


def test_mark_failed_for_never_upserted_doc_inserts_row(store: MetadataStore):
    # Regression: mark_failed previously used cumulative total_changes which
    # silently skipped the fallback insert when called on a doc that was never
    # upserted.
    store.mark_failed("localfs", "default", "ghost", reason="download error")
    row = store.get_document("localfs", "default", "ghost")
    assert row is not None
    assert row["status"] == "failed"
    assert row["failure_reason"] == "download error"
