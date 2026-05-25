# Super RAG — Architecture

**Last updated:** 2026-05-24
**Phase:** 1 (Local-files MVP) complete; Phase 2 (cloud connectors) pending.

## Pipeline

```
                              SYNC PATH
   ┌──────────────┐   ChangeEvent   ┌──────────┐  RawDoc   ┌────────┐
   │  Connector   │ ──────────────► │   sync   │ ────────► │ parser │
   │  (localfs)   │ ◄── fetch ───── │ (orchestr)│           └───┬────┘
   └──────────────┘                 └──────────┘               │ ParsedDoc
                                          │                    ▼
                                          │              ┌──────────┐
                                          │              │ chunker  │
                                          │              └───┬──────┘
                                          │                  │ list[Chunk]
                                          │                  ▼
                          ┌──────────┐    │             ┌──────────┐
                          │ embedder │◄───┴──── texts ──┤  chunks  │
                          │ (Ollama) │                  └─────┬────┘
                          └────┬─────┘                        │
                               │ float32[n,384]               │ rows
                               ▼                              ▼
                         ┌───────────┐                 ┌─────────────┐
                         │  index    │                 │  metadata   │
                         │ (turbovec)│                 │  (sqlite)   │
                         └───────────┘                 └─────────────┘
                                  ▲          failures        │
                                  │                          ▼
                                  │                    ┌──────────┐
                                  │                    │   dlq    │
                                  │                    │  (jsonl) │
                                  │                    └──────────┘
                              QUERY PATH
   user q ──► route_query ──► embedder.embed_query ──► index.search
                                                            │
                                                            │ chunk_ids+scores
                                                            ▼
                                                metadata.hydrate_chunks
                                                            │
                                                            │ context
                                                            ▼
                                         LLMBackend (claude-cli | ollama)
                                                            │
                                                            ▼
                                                     Answer + Citations
```

## Component responsibilities

**parser** (`rag/parser.py`) — Turns a `RawDoc` into a `ParsedDoc` with `text` plus `page_texts`. PDFs go through PyMuPDF; when average characters-per-page falls below `min_chars_per_page` (auto-detect strategy) or on `always`, the parser lazily imports `pdf2image` + `pytesseract` for OCR. DOCX is read via `python-docx`; `text/plain` and `text/markdown` are decoded directly.

**chunker** (`rag/chunker.py`) — Wraps LlamaIndex's `SentenceSplitter` and back-maps each chunk to a `(first_page, last_page)` range by scanning a character cursor over the joined page texts. Mints the canonical `chunk_id`.

**embedder** (`rag/embedder.py`) — Thin `httpx` client over the Ollama `/api/embeddings` endpoint. `embed_query` is used at query time, `embed_batch` at ingest. Same model is used on both sides — guaranteed by passing one `OllamaEmbedder` instance to both orchestrators.

**index** (`rag/index.py`) — `VectorIndex` wraps `turbovec.IdMapIndex`. Maintains its own `str ↔ uint64` map (turbovec only accepts uint64 ids) persisted as a JSON sidecar next to the `.tvim` file. Supports `add_batch`, `delete_by_doc_id` (prefix match on `source:account:doc_id:`), `search`, `save`/`load`. Enforces `dim % 8 == 0`.

**metadata** (`rag/metadata.py`) — SQLite store with three tables: `documents` (one row per source/account/doc, tracks content hash + status), `chunks` (text + page range + source_url, hydrated at query time), `runs` (per-sync run summary, used to compute `since` watermark). All writes commit immediately.

**dlq** (`rag/dlq.py`) — Append-only JSONL of `(doc_id, source, account, error, traceback, retry_count, first_failed_at, last_failed_at)`. Deduplicates on `(doc_id, source, account)`. `mark_retried` rewrites the file in place.

**sync** (`rag/sync.py`) — `SyncOrchestrator.run()` opens a run row, iterates connectors × accounts, applies deltas since the last successful run, and per-document: hashes content, skips if hash matches an existing indexed row, parses → chunks → embeds → atomically swaps vectors and chunk rows for that doc. Failures are isolated per-doc and land in the DLQ; per-account auth/list failures are logged but don't abort the run.

**query** (`rag/query.py`) — `QueryEngine.ask()` strips the private prefix, embeds the cleaned question, top-k searches the vector index, hydrates the chunk rows from SQLite while preserving rank order, builds a context block with `[Source: …]` headers, picks the backend (Claude CLI by default; Ollama when private), and returns an `Answer` with `Citation`s.

**llm** (`rag/llm.py`) — `LLMBackend` Protocol with two concrete implementations: `ClaudeCLIBackend` shells out to `claude --print` (reuses the user's Max-tier auth, no API key), `OllamaBackend` POSTs `/api/chat`. `route_query` is a pure function returning `(cleaned_text, is_private)`.

**connectors** (`rag/connectors/`) — `Connector` Protocol plus `LocalfsConnector`. The local connector walks configured roots for supported extensions (`.pdf .txt .md .docx`), filters by `since`, and writes a `.rag-localfs-manifest.json` per root so deletes between runs surface as `ChangeEvent(operation="delete")`.

**serve.cli** (`rag/serve/cli.py`) — Click CLI: `rag sync`, `rag query`, `rag status`, `rag dlq list`. Wires config → stores → orchestrator/engine. Rich-formatted output.

## Data contracts (`rag/types.py`)

All inter-component payloads are frozen dataclasses:

| Dataclass | Carries | Produced by | Consumed by |
|-----------|---------|-------------|-------------|
| `ChangeEvent` | source, account, doc_id, operation, source_url, last_modified | connector | sync |
| `RawDoc` | doc_id, mime, content bytes, filename, last_modified | connector.fetch_content | parser |
| `ParsedDoc` | text, page_texts, metadata | parser | chunker |
| `Chunk` | chunk_id, doc_id, chunk_idx, text, page_range, source_url | chunker | embedder, index, metadata |
| `Citation` | chunk_id, source_url, excerpt, page, score | query | CLI |
| `Answer` | text, citations, private | query | CLI |

## Identifier conventions

- **`doc_id`** is connector-defined and source-stable. For `localfs` it is the absolute path string.
- **`chunk_id`** is canonical: `"{source}:{account}:{doc_id}:{idx:05d}"`. The 5-digit zero-padded index keeps lexicographic order matching numeric order up to 100k chunks/doc. The index's `delete_by_doc_id` relies on the `source:account:doc_id:` prefix, and `metadata.upsert_chunks` parses the prefix back out.
- **`account`** is a connector-scoped alias (e.g. `"default"` for local, `"personal-jeremy"` for cloud accounts in Phase 2).
- **`source`** is the connector's `name` attribute (`"localfs"`, future: `"gdrive"`, `"onedrive"`, `"gmail"`, `"outlook"`).

## Extension points

**Adding a new source.** Implement the `Connector` Protocol from `rag/connectors/__init__.py`:

```python
class MyConnector:
    name = "mysource"
    def list_changes(self, account, since) -> Iterator[ChangeEvent]: ...
    def fetch_content(self, account, doc_id) -> RawDoc: ...
```

Contract: `list_changes` must be idempotent, never raise on missing docs (emit `operation="delete"` instead), and raise `ConnectorAuthError` for auth failures so the orchestrator can continue past it. Register the connector + accounts in `serve/cli.py::sync` and add a matching `SourceConfig` subclass in `rag/config.py`.

**Adding a new LLM backend.** Implement `LLMBackend` from `rag/llm.py`:

```python
class MyBackend:
    def generate(self, system: str, user: str) -> str: ...
```

Pass it into `QueryEngine` alongside (or instead of) Claude/Ollama. Routing logic in `QueryEngine.ask` may need updating if the new backend is to participate in private-mode routing.

**Swapping the vector store.** The `VectorIndex` public surface (`add_batch`, `delete_by_doc_id`, `search`, `save`, `load`) is the contract — anything providing those methods plus a `dim` attribute can substitute for turbovec. Persistence layout (sidecar JSON for str↔uint64 mapping) is a turbovec-specific implementation detail.
