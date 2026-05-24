from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest
from rag.sync import SyncOrchestrator
from rag.types import ChangeEvent, RawDoc


@pytest.fixture
def fake_embedder():
    emb = MagicMock()
    emb.embed_batch.side_effect = lambda texts: [[0.1, 0.2, 0.3, 0.4]] * len(texts)
    return emb


@pytest.fixture
def fake_index():
    idx = MagicMock()
    return idx


@pytest.fixture
def fake_connector(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello orchestrator", encoding="utf-8")

    conn = MagicMock()
    conn.name = "localfs"
    conn.list_changes.return_value = iter([
        ChangeEvent(source="localfs", account="default", doc_id=str(f),
                    operation="upsert", source_url=f.as_uri(),
                    last_modified=datetime(2026, 5, 23), size_bytes=f.stat().st_size,
                    mime="text/plain"),
    ])
    conn.fetch_content.return_value = RawDoc(
        doc_id=str(f), source="localfs", account="default",
        source_url=f.as_uri(), mime="text/plain",
        content=b"hello orchestrator", filename=f.name,
        last_modified=datetime(2026, 5, 23),
    )
    return conn


def test_orchestrator_indexes_one_doc(tmp_path: Path, fake_connector, fake_embedder, fake_index):
    from rag.metadata import MetadataStore
    from rag.dlq import DeadLetterQueue
    meta = MetadataStore(tmp_path / "meta.sqlite")
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")

    orch = SyncOrchestrator(
        connectors={"localfs": fake_connector},
        accounts_per_connector={"localfs": ["default"]},
        embedder=fake_embedder, index=fake_index,
        metadata=meta, dlq=dlq,
        chunk_size=512, overlap=64, ocr_strategy="never",
    )
    result = orch.run()
    assert result.docs_processed == 1
    assert result.chunks_indexed >= 1
    assert result.docs_failed == 0
    fake_index.add_batch.assert_called_once()


def test_orchestrator_isolates_per_doc_failure(tmp_path: Path, fake_embedder, fake_index):
    from rag.metadata import MetadataStore
    from rag.dlq import DeadLetterQueue
    meta = MetadataStore(tmp_path / "meta.sqlite")
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")

    good = tmp_path / "good.txt"; good.write_text("ok", encoding="utf-8")
    bad = tmp_path / "bad.txt"; bad.write_text("boom", encoding="utf-8")

    conn = MagicMock()
    conn.name = "localfs"
    conn.list_changes.return_value = iter([
        ChangeEvent(source="localfs", account="default", doc_id=str(good),
                    operation="upsert", source_url=good.as_uri(),
                    last_modified=datetime(2026, 5, 23), mime="text/plain"),
        ChangeEvent(source="localfs", account="default", doc_id=str(bad),
                    operation="upsert", source_url=bad.as_uri(),
                    last_modified=datetime(2026, 5, 23), mime="text/plain"),
    ])

    def fetch(account, doc_id):
        if "bad" in doc_id:
            raise OSError("simulated read failure")
        return RawDoc(doc_id=doc_id, source="localfs", account=account,
                      source_url=Path(doc_id).as_uri(), mime="text/plain",
                      content=b"ok", filename=Path(doc_id).name,
                      last_modified=datetime(2026, 5, 23))
    conn.fetch_content.side_effect = fetch

    orch = SyncOrchestrator(
        connectors={"localfs": conn}, accounts_per_connector={"localfs": ["default"]},
        embedder=fake_embedder, index=fake_index,
        metadata=meta, dlq=dlq,
        chunk_size=512, overlap=64, ocr_strategy="never",
    )
    result = orch.run()
    assert result.docs_processed == 1
    assert result.docs_failed == 1
    assert len(list(dlq.iter_entries())) == 1
