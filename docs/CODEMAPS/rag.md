# Codemap — `src/rag/`

**Last updated:** 2026-05-30
**Scope:** Every Python module under `src/rag/`. Use this to find the right file fast.

## Module index

| File | One-liner |
|------|-----------|
| `__init__.py` | Package marker; exposes `__version__ = "0.1.0"`. |
| `types.py` | Shared dataclasses: `ChangeEvent`, `RawDoc`, `ParsedDoc`, `Chunk`, `Citation`, `Answer`. |
| `config.py` | Pydantic config schema + `load_config(path)` YAML loader. |
| `parser.py` | `parse(raw, ocr_strategy, min_chars_per_page)` — PDF/DOCX/text to `ParsedDoc`. |
| `chunker.py` | `chunk_document(parsed, source, account, source_url, chunk_size, overlap)` — sentence chunking with page-range mapping. |
| `embedder.py` | `OllamaEmbedder` — `embed_query`, `embed_batch` against Ollama. |
| `index.py` | `VectorIndex` — turbovec wrapper with stable string IDs, doc-prefix deletes, save/load. |
| `metadata.py` | `MetadataStore` — SQLite for documents/chunks/runs; hydrate at query time. |
| `dlq.py` | `DeadLetterQueue` — JSONL append-only failure log. |
| `sync.py` | `SyncOrchestrator`, `RunResult` — drives the full ingest pipeline. |
| `llm.py` | `LLMBackend` Protocol, `ClaudeCLIBackend`, `OllamaBackend`, `route_query`. |
| `query.py` | `QueryEngine.ask(question) -> Answer` — embed/retrieve/hydrate/generate. |
| `connectors/__init__.py` | `Connector` Protocol, `ConnectorError`, `ConnectorAuthError`, `ConnectorRateLimitError`. |
| `connectors/localfs.py` | `LocalfsConnector` — walks roots, manifest-based delete detection. |
| `connectors/_cloud.py` | Shared cloud helpers: `CloudItem`, `ManifestStore`, `diff_items`, `resolve_connected_account`, and the download layer `download_bytes`/`resolve_bytes`/`dig` (presigned `s3url` → bytes). |
| `connectors/composio_client.py` | `ComposioClient` Protocol, `unwrap_response` (envelope→data + typed errors), `ComposioSDKClient` (real SDK binding, integration-gated). |
| `connectors/gdrive.py` | `GdriveConnector` — `GOOGLEDRIVE_FIND_FILE`/`GOOGLEDRIVE_DOWNLOAD_FILE`. |
| `connectors/onedrive.py` | `OneDriveConnector` — recursive `ONE_DRIVE_LIST_FOLDER_CHILDREN` + `ONE_DRIVE_DOWNLOAD_FILE`. |
| `connectors/gmail.py` | `GmailConnector` — attachments only; fetch-emails + per-message hydrate + `GMAIL_GET_ATTACHMENT`. |
| `connectors/outlook.py` | `OutlookConnector` — attachments only; search + list-attachments + `OUTLOOK_DOWNLOAD_OUTLOOK_ATTACHMENT`. |
| `serve/__init__.py` | Package marker. |
| `serve/cli.py` | Click CLI: `sync`, `query`, `status`, `dlq list`, `dlq replay`; wires all connectors. |

---

## File-by-file

### `types.py`
**Public:** `ChangeEvent`, `RawDoc`, `ParsedDoc`, `Chunk`, `Citation`, `Answer` (all `@dataclass`).
**Depended on by:** every other module in the package — this is the contract layer. Never imports from sibling modules.

### `config.py`
**Public:** `Config`, `LocalfsSource`, `GdriveSource`, `OneDriveSource`, `GmailSource`, `OutlookSource`, `EmbeddingConfig`, `ChunkingConfig`, `OcrConfig`, `LlmConfig`, `PathsConfig`, `SourceConfig` (union), `load_config(path) -> Config`.
**Depended on by:** `serve/cli.py`. Source subclasses are dispatched by `kind` discriminator in a pre-validator.

### `parser.py`
**Public:** `parse(raw: RawDoc, ocr_strategy, min_chars_per_page) -> ParsedDoc`.
**Internal:** `_parse_pdf`, `_parse_docx`, `_parse_text`, `_ocr_pdf` (lazy-imports OCR deps).
**Depended on by:** `sync.py`. Imports `types.RawDoc`, `types.ParsedDoc`.

### `chunker.py`
**Public:** `chunk_document(parsed, source, account, source_url, chunk_size=512, overlap=64) -> list[Chunk]`.
**Internal:** local helper `page_range_for` derives 1-based inclusive `(first, last)` page range per chunk.
**Depended on by:** `sync.py`. Mints the canonical `chunk_id` format `"{source}:{account}:{doc_id}:{idx:05d}"`.

### `embedder.py`
**Public:** `OllamaEmbedder(model, base_url, batch_size, timeout)` with `embed_query`, `embed_batch`, `close`.
**Depended on by:** `sync.py`, `query.py`, `serve/cli.py`. Same instance is shared by both orchestrators to guarantee identical embeddings at ingest and query.

### `index.py`
**Public:** `VectorIndex(dim, path)`, `VectorIndex.load(dim, path)`, `add_batch(ids, vectors)`, `delete_by_doc_id(source, account, doc_id)`, `search(query, k)`, `save()`.
**Internal:** `_str_to_int`, `_int_to_str`, `_counter`, `_sidecar_path()`. Sidecar persisted at `<index>.idmap.json`.
**Depended on by:** `sync.py`, `query.py`, `serve/cli.py`. Wraps `turbovec.IdMapIndex` (requires `dim % 8 == 0`, uint64 ids).

### `metadata.py`
**Public:** `MetadataStore(db_path)` with `upsert_document`, `mark_failed`, `mark_deleted`, `get_document`, `upsert_chunks`, `hydrate_chunks`, `start_run`, `finish_run`, `list_runs`, `last_successful_run_at`, `close`.
**Schema:** `documents` (PK source+account+doc_id), `chunks` (PK chunk_id, FK to documents), `runs` (autoincr id).
**Depended on by:** `sync.py`, `query.py`, `serve/cli.py`.

### `dlq.py`
**Public:** `DeadLetterQueue(path)` with `write`, `iter_entries(source=None)`, `mark_retried`.
**Format:** JSONL; dedup key is `(doc_id, source, account)`.
**Depended on by:** `sync.py`, `serve/cli.py`.

### `llm.py`
**Public:** `LLMBackend` Protocol (`generate(system, user) -> str`), `ClaudeCLIBackend(command, timeout)`, `OllamaBackend(model, base_url, timeout)`, `route_query(raw, claude, ollama, private_prefix, default, private_routes_to) -> (cleaned, is_private)`.
**Depended on by:** `query.py`, `serve/cli.py`. `ClaudeCLIBackend` shells out to `claude --print`; `OllamaBackend` POSTs `/api/chat`.

### `query.py`
**Public:** `QueryEngine(embedder, index, metadata, claude, ollama, top_k, private_prefix, default_backend, private_routes_to)` with `ask(question) -> Answer`.
**Imports:** `llm` (LLMBackend, route_query), `types` (Answer, Citation); TYPE_CHECKING: `embedder`, `index`, `metadata`.
**Depended on by:** `serve/cli.py`. Holds the canonical system prompt constant `_SYSTEM_PROMPT`.

### `connectors/__init__.py`
**Public:** `Connector` Protocol (`name`, `list_changes(account, since)`, `fetch_content(account, doc_id)`), `ConnectorError`, `ConnectorAuthError`, `ConnectorRateLimitError`.
**Depended on by:** `sync.py` (uses Protocol + ConnectorAuthError), `connectors/localfs.py` (implements).

### `connectors/localfs.py`
**Public:** `LocalfsConnector(roots: list[Path])` with `name="localfs"`, `list_changes(account, since)`, `fetch_content(account, doc_id)`.
**Internal:** `_scan_root`, `_MANIFEST_NAME = ".rag-localfs-manifest.json"`, `_SUPPORTED_EXTS = {.pdf, .txt, .md, .docx}`.
**Depended on by:** `serve/cli.py`. Writes a per-root manifest so deletes between runs are observable.

### `connectors/_cloud.py`
**Public:** `CloudItem` (pre-fetch listing item), `ManifestStore` (per-(source,account) snapshot for delete detection), `diff_items(...)` (current set → upsert/delete `ChangeEvent`s, mirrors localfs), `resolve_connected_account`, and the download layer: `download_bytes(url)` (httpx GET of a presigned URL), `resolve_bytes(data, s3url_path, b64_path=…)` (prefer s3url, fall back to inline base64), `dig(data, "a.b.c")`.
**Depended on by:** all four cloud connectors. The s3url two-step download is the central contract: Composio download actions return a short-lived locator, not inline bytes.

### `connectors/composio_client.py`
**Public:** `ComposioClient` Protocol (`execute(action, params, *, connected_account_id)`), `unwrap_response(resp)` (envelope→`data`, maps auth/rate errors), `ComposioSDKClient(api_key)` (real binding; lazy-imports `composio`, integration-gated).
**Depended on by:** cloud connectors (via Protocol — kept SDK-free for unit tests), `serve/cli.py` (builds the real client).

### `connectors/{gdrive,onedrive,gmail,outlook}.py`
**Public:** `GdriveConnector`, `OneDriveConnector`, `GmailConnector`, `OutlookConnector` — each `(client, connected_accounts, state_dir, …filters)` implementing the `Connector` Protocol. Drive/OneDrive index files; Gmail/Outlook index attachments only (`doc_id="{message_id}:{attachment_id}"`). All downloads resolve through `_cloud.resolve_bytes`.
**Depended on by:** `serve/cli.py`. Listing/download contract verified against the live Composio API (Drive + Outlook end-to-end; Gmail/OneDrive at schema level).

### `sync.py`
**Public:** `SyncOrchestrator(...)` with `run() -> RunResult` and `replay_doc(source, account, doc_id) -> int` (DLQ reprocessing); `RunResult(...)`.
**Internal:** `_process_doc(conn, event)` does fetch → hash → skip-if-unchanged → parse → chunk → embed → index swap → metadata upsert.
**Depended on by:** `serve/cli.py`.

### `serve/cli.py`
**Public:** `main` (Click group) with subcommands `sync`, `query`, `status`, `dlq list`, `dlq replay`.
**Internal:** `_build(cfg_path)` wires `Config → MetadataStore + DLQ + VectorIndex + OllamaEmbedder`; `_build_connectors(cfg)` instantiates every source kind (lazy-builds one shared `ComposioSDKClient` for cloud sources; manifests under `bundle_dir/manifests`); `_CLOUD_KINDS` registry; `_INDEX_DIM = 384`.
**Depended on by:** packaged entrypoint `rag` (see `pyproject.toml`).

---

## Dependency graph (intra-package)

```
types ◄──────── (everything)

config ◄────── serve/cli

parser ──┐
chunker ─┼──► sync ──► serve/cli
embedder ┤        │
index ───┤        │
metadata ┤        │
dlq ─────┤        │
connectors/* ────┘

embedder ┐
index ───┼──► query ──► serve/cli
metadata ┤      ▲
llm ─────┴──────┘
```

Modules with **no intra-package deps** beyond `types`: `parser`, `chunker`, `embedder`, `index`, `metadata`, `dlq`, `llm`, `connectors/__init__`, `connectors/localfs`. This is by design — orchestration is concentrated in `sync.py`, `query.py`, and `serve/cli.py`.
