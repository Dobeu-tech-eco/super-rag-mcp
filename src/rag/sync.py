"""Sync orchestrator: walks connectors, parses, chunks, embeds, indexes."""
from __future__ import annotations

import hashlib
import logging
import traceback
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from rag.chunker import chunk_document
from rag.connectors import Connector, ConnectorAuthError
from rag.dlq import DeadLetterQueue
from rag.metadata import MetadataStore
from rag.parser import parse
from rag.types import ChangeEvent

if TYPE_CHECKING:
    from rag.embedder import OllamaEmbedder
    from rag.index import VectorIndex

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    docs_processed: int
    docs_failed: int
    chunks_indexed: int


class SyncOrchestrator:
    def __init__(
        self,
        connectors: dict[str, Connector],
        accounts_per_connector: dict[str, list[str]],
        embedder: OllamaEmbedder,
        index: VectorIndex,
        metadata: MetadataStore,
        dlq: DeadLetterQueue,
        chunk_size: int = 512,
        overlap: int = 64,
        ocr_strategy: str = "auto_detect",
    ) -> None:
        self.connectors = connectors
        self.accounts_per_connector = accounts_per_connector
        self.embedder = embedder
        self.index = index
        self.metadata = metadata
        self.dlq = dlq
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.ocr_strategy = ocr_strategy

    def run(self) -> RunResult:
        run_id = self.metadata.start_run()
        docs_processed = 0
        docs_failed = 0
        chunks_indexed = 0
        try:
            since = self.metadata.last_successful_run_at()
            for source_name, conn in self.connectors.items():
                accounts = self.accounts_per_connector.get(source_name, [])
                for account in accounts:
                    try:
                        events: Iterable[ChangeEvent] = conn.list_changes(account, since)
                    except ConnectorAuthError as e:
                        log.error("auth error for %s/%s: %s", source_name, account, e)
                        continue
                    except Exception:
                        log.exception("listing failed for %s/%s", source_name, account)
                        continue

                    for event in events:
                        if event.operation == "delete":
                            self.metadata.mark_deleted(event.source, event.account, event.doc_id)
                            self.index.delete_by_doc_id(event.source, event.account, event.doc_id)
                            continue
                        try:
                            chunks_added = self._process_doc(conn, event)
                            docs_processed += 1
                            chunks_indexed += chunks_added
                        except Exception as e:
                            docs_failed += 1
                            tb = traceback.format_exc()
                            log.warning(
                                "doc failed: %s/%s/%s: %s",
                                event.source, event.account, event.doc_id, e,
                            )
                            self.dlq.write(
                                doc_id=event.doc_id, source=event.source,
                                account=event.account, error=str(e), traceback_str=tb,
                            )
                            self.metadata.mark_failed(
                                event.source, event.account, event.doc_id, reason=str(e)
                            )
            self.metadata.finish_run(
                run_id, status="success",
                docs_processed=docs_processed, chunks_indexed=chunks_indexed,
            )
            return RunResult(docs_processed, docs_failed, chunks_indexed)
        except Exception:
            self.metadata.finish_run(
                run_id, status="crashed",
                docs_processed=docs_processed, chunks_indexed=chunks_indexed,
            )
            raise

    def replay_doc(self, source: str, account: str, doc_id: str) -> int:
        """Re-fetch and re-index one previously-failed document. Returns chunks added.

        Used by ``rag dlq replay``. The DLQ entry carries only (source, account, doc_id),
        so the synthesized event has no ``source_url`` — citations for replayed docs lose
        the link, but the content is re-indexed.
        """
        conn = self.connectors.get(source)
        if conn is None:
            raise KeyError(f"no connector configured for source {source!r}")
        event = ChangeEvent(
            source=source,
            account=account,
            doc_id=doc_id,
            operation="upsert",
            source_url="",
            last_modified=datetime.utcnow(),
        )
        return self._process_doc(conn, event)

    def _process_doc(self, conn: Connector, event: ChangeEvent) -> int:
        raw = conn.fetch_content(event.account, event.doc_id)
        content_hash = hashlib.sha256(raw.content).hexdigest()
        existing = self.metadata.get_document(event.source, event.account, event.doc_id)
        if existing and existing["content_hash"] == content_hash and existing["status"] == "indexed":
            return 0  # idempotent skip

        parsed = parse(raw, ocr_strategy=self.ocr_strategy)
        chunks = chunk_document(
            parsed,
            source=event.source,
            account=event.account,
            source_url=event.source_url,
            chunk_size=self.chunk_size,
            overlap=self.overlap,
        )
        if not chunks:
            self.metadata.upsert_document(event, content_hash=content_hash)
            return 0

        vectors = self.embedder.embed_batch([c.text for c in chunks])
        # Delete prior chunks for this doc, then add fresh.
        self.index.delete_by_doc_id(event.source, event.account, event.doc_id)
        self.index.add_batch(
            [c.chunk_id for c in chunks],
            np.array(vectors, dtype=np.float32),
        )
        self.metadata.upsert_document(event, content_hash=content_hash)
        self.metadata.upsert_chunks(chunks)
        return len(chunks)
