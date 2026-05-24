"""SQLite-backed metadata store: documents, chunks, runs."""
from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from rag.types import ChangeEvent, Chunk


_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    source TEXT NOT NULL,
    account TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    mime TEXT,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER,
    last_modified TEXT,
    last_synced TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('indexed','failed','deleted')),
    failure_reason TEXT,
    PRIMARY KEY (source, account, doc_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    source TEXT NOT NULL,
    account TEXT NOT NULL,
    chunk_idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    source_url TEXT NOT NULL,
    FOREIGN KEY (source, account, doc_id) REFERENCES documents(source, account, doc_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(source, account, doc_id);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    docs_processed INTEGER DEFAULT 0,
    chunks_indexed INTEGER DEFAULT 0,
    last_resumable_at TEXT
);
"""


class MetadataStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ----- documents -----

    def upsert_document(self, event: ChangeEvent, content_hash: str) -> None:
        now = datetime.utcnow().isoformat()
        self._conn.execute(
            """INSERT INTO documents (source, account, doc_id, source_url, mime,
                content_hash, size_bytes, last_modified, last_synced, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed')
               ON CONFLICT(source, account, doc_id) DO UPDATE SET
                source_url=excluded.source_url, mime=excluded.mime,
                content_hash=excluded.content_hash, size_bytes=excluded.size_bytes,
                last_modified=excluded.last_modified, last_synced=excluded.last_synced,
                status='indexed', failure_reason=NULL""",
            (event.source, event.account, event.doc_id, event.source_url, event.mime,
             content_hash, event.size_bytes, event.last_modified.isoformat(), now),
        )
        self._conn.commit()

    def mark_failed(self, source: str, account: str, doc_id: str, reason: str) -> None:
        cur = self._conn.execute(
            "UPDATE documents SET status='failed', failure_reason=? "
            "WHERE source=? AND account=? AND doc_id=?",
            (reason, source, account, doc_id),
        )
        if cur.rowcount == 0:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                """INSERT OR IGNORE INTO documents
                    (source, account, doc_id, source_url, content_hash, last_synced, status, failure_reason)
                   VALUES (?, ?, ?, '', '', ?, 'failed', ?)""",
                (source, account, doc_id, now, reason),
            )
        self._conn.commit()

    def mark_deleted(self, source: str, account: str, doc_id: str) -> None:
        self._conn.execute(
            "UPDATE documents SET status='deleted' WHERE source=? AND account=? AND doc_id=?",
            (source, account, doc_id),
        )
        self._conn.execute(
            "DELETE FROM chunks WHERE source=? AND account=? AND doc_id=?",
            (source, account, doc_id),
        )
        self._conn.commit()

    def get_document(self, source: str, account: str, doc_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE source=? AND account=? AND doc_id=?",
            (source, account, doc_id),
        ).fetchone()
        return dict(row) if row else None

    # ----- chunks -----

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        rows = []
        for c in chunks:
            parsed_id = c.chunk_id.split(":")
            if len(parsed_id) < 4:
                raise ValueError(f"chunk_id must be source:account:doc:idx, got {c.chunk_id}")
            src, acct = parsed_id[0], parsed_id[1]
            page_start, page_end = (c.page_range or (None, None))
            rows.append((c.chunk_id, c.doc_id, src, acct, c.chunk_idx,
                         c.text, page_start, page_end, c.source_url))
        self._conn.executemany(
            """INSERT INTO chunks (chunk_id, doc_id, source, account, chunk_idx,
                                   text, page_start, page_end, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(chunk_id) DO UPDATE SET
                   text=excluded.text, page_start=excluded.page_start,
                   page_end=excluded.page_end""",
            rows,
        )
        self._conn.commit()

    def hydrate_chunks(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        qmarks = ",".join("?" * len(chunk_ids))
        rows = self._conn.execute(
            f"SELECT * FROM chunks WHERE chunk_id IN ({qmarks})",
            chunk_ids,
        ).fetchall()
        return [dict(r) for r in rows]

    # ----- runs -----

    def start_run(self) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (started_at) VALUES (?)",
            (datetime.utcnow().isoformat(),),
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, status: str, docs_processed: int,
                   chunks_indexed: int, last_resumable_at: str | None = None) -> None:
        self._conn.execute(
            """UPDATE runs SET finished_at=?, status=?, docs_processed=?,
                               chunks_indexed=?, last_resumable_at=?
               WHERE id=?""",
            (datetime.utcnow().isoformat(), status, docs_processed,
             chunks_indexed, last_resumable_at, run_id),
        )
        self._conn.commit()

    def list_runs(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def last_successful_run_at(self) -> datetime | None:
        row = self._conn.execute(
            "SELECT finished_at FROM runs WHERE status='success' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return datetime.fromisoformat(row["finished_at"]) if row else None
