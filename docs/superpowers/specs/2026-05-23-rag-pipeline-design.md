# RAG Pipeline Design — Super RAG: GDrive + OneDrive + Email + Local

**Status:** Approved (sections 1-5)
**Date:** 2026-05-23
**Owner:** Jeremy Williams (jswilliamstu@gmail.com)
**Repo:** `C:\Users\jswil\repos\super-rag-gdrive-onedrive`

## 1. Purpose

Build a self-hosted retrieval-augmented generation pipeline that indexes documents — especially PDFs — from the user's Google Drive accounts, OneDrive accounts, Gmail and Outlook attachments, and selected local folders. The agent answers natural-language questions with citations back to the originating document. The system must run on commodity hardware, cost roughly the price of a small VPS per month plus existing Claude Max usage, and remain fully recoverable from any single failure.

## 2. Goals and Non-Goals

**Goals**

- Index 50K to 500K documents across multiple Google Drive and OneDrive accounts, plus Gmail and Outlook attachments, plus designated local folders.
- OCR all image-based PDFs so scanned archives become searchable.
- Sync nightly with no manual intervention required.
- Answer queries with citations that link back to the original document URL or path.
- Expose the agent through both a CLI and a Cowork-compatible MCP server.
- Default to Claude (via the Max subscription Claude Code CLI) for generation, with a local Ollama fallback for queries flagged private.
- Per-source and per-document failure isolation — one bad PDF or one expired auth token never aborts the whole run.

**Non-goals**

- Real-time indexing under one minute of source modification (nightly is sufficient).
- Multi-user access controls (single-user system).
- Mobile clients.
- Indexing of media files (images, audio, video) for content. Image-bearing PDFs are OCRed for text only.
- Vector search over very large (greater than 1M document) corpora — TurboVec is sized for the stated range.

## 3. Architecture

Two physical hosts connected over Tailscale: a VPS that owns the ingest plane, and the MSI laptop that owns the query plane. The only thing crossing the boundary at runtime is the nightly index bundle.

**VPS — ingest plane.** A long-lived Linux service. A systemd timer fires the orchestrator nightly at 03:00 local. The orchestrator walks each configured source via Composio (or the filesystem for local), asks for deltas since the last successful run, parses changed documents, OCRs scanned PDFs when needed, chunks text, embeds chunks against a locally hosted Ollama BGE-small model, and writes vectors into a TurboVec `IdMapIndex` while updating a SQLite metadata sidecar. The run produces a versioned bundle:
`/var/lib/rag/bundles/run-YYYYMMDD/{index.tq, meta.sqlite, manifest.json}`.

**Laptop — query plane.** Two services. `rag-sync` polls the VPS bundle directory over Tailscale (rsync `--link-dest` to deduplicate unchanged shards) and atomically swaps in the newest bundle via a `current` symlink. The prior bundle is kept on disk for rollback. `rag-server` holds the active index in memory and serves queries via the CLI and the MCP server. A query embeds with the same BGE-small model running in laptop-side Ollama, does top-k over TurboVec, optionally re-ranks with a cross-encoder, then routes to either the Claude Code CLI or local Ollama based on a per-query `private:` tag.

**Failure isolation.** Two boundaries: per-source (one broken connector never poisons other sources) and per-document (one corrupt PDF never aborts the run). Both are enforced with explicit try/except plus a dead-letter queue. Never `except: pass`.

**Network.** Tailscale provides mutually authenticated mesh networking with no public ports. Free tier is sufficient.

## 4. Components

Eleven Python packages under `src/rag/`, each owning one responsibility:

1. **`rag.connectors.{gdrive, onedrive, gmail, outlook, localfs}`** — one module per source. Each implements `Connector` protocol: `list_changes(since: datetime) -> Iterator[ChangeEvent]` and `fetch_content(doc_id) -> RawDoc`. Composio is the auth and transport for cloud sources; `localfs` walks the filesystem. Multi-account is handled via account alias in config.

2. **`rag.parser`** — accepts `RawDoc`, returns `ParsedDoc(text, page_map, metadata)`. Routes by MIME: `pymupdf` for text PDFs, `pdfplumber` as secondary, `tesseract` via `pytesseract` + `pdf2image` for scanned PDFs, `python-docx`, `python-pptx`, `openpyxl`, `markdown-it`. Detects scanned PDFs heuristically: if text extraction yields under 100 characters per page on average, the OCR path is taken.

3. **`rag.chunker`** — LlamaIndex `SemanticSplitterNodeParser` as the primary, with `SentenceSplitter(chunk_size=512, chunk_overlap=64)` as deterministic fallback. Emits `Chunk(text, doc_id, chunk_idx, page_range, source_url)`.

4. **`rag.embedder`** — wraps an Ollama HTTP client pinned to `bge-small-en-v1.5`. Batches in groups of 32. The identical interface runs on the VPS (ingest) and the laptop (query embedding) — guaranteeing vector-space consistency.

5. **`rag.index`** — thin wrapper over `turbovec.IdMapIndex`. Stable string IDs of the form `{source}:{account_alias}:{doc_id}:{chunk_idx}`. Exposes `add_batch`, `delete_by_doc_id`, `search(query_vec, k)`.

6. **`rag.metadata`** — SQLite via `sqlite-utils`. Three tables: `documents` (doc-level state: source, account_alias, doc_id, hash, last_synced, source_url, status), `chunks` (chunk_id → doc_id → page_range), `runs` (orchestrator run log: started_at, finished_at, status, last_resumable_at).

7. **`rag.sync`** — the orchestrator. Reads `config.yaml`, iterates connectors, runs parse→chunk→embed→index. Resumable via run-log checkpoints every 1000 documents. Atomic bundle output.

8. **`rag.dlq`** — dead-letter queue for failed docs. JSONL at `/var/lib/rag/dlq.jsonl` with `{doc_id, source, account, error, traceback, retry_count, last_failed_at}`. Re-runnable as a standalone command.

9. **`rag.query`** — query-side library: embed → retrieve → rerank → synthesize. Returns `Answer(text, citations: list[Citation])` where each Citation contains `source_url`, `excerpt`, `page`, `score`.

10. **`rag.llm`** — generation backends. `ClaudeCLIBackend` shells out to `claude` using Max auth. `OllamaBackend` for private-tagged queries. Selected per query.

11. **`rag.serve.{cli, mcp}`** — `cli` exposes `rag query "..."`, `rag sync`, `rag dlq replay`, `rag status`. `mcp` is a `fastmcp` server registering `search_docs`, `get_doc`, `list_sources`, `force_sync` for Cowork to call.

**Repository layout**

```
super-rag-gdrive-onedrive/
├── pyproject.toml
├── config.example.yaml
├── README.md
├── docs/superpowers/specs/
├── src/rag/
│   ├── connectors/{gdrive,onedrive,gmail,outlook,localfs}.py
│   ├── parser.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── index.py
│   ├── metadata.py
│   ├── sync.py
│   ├── dlq.py
│   ├── query.py
│   ├── llm.py
│   └── serve/{cli.py, mcp.py}
├── deploy/
│   ├── vps/         # systemd units, install.sh, Tailscale notes
│   └── laptop/      # systemd-user units (or Task Scheduler on Windows), install.sh
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── eval/
│   └── fixtures/
└── .agent/{progress.md, tasks.json, state.json}
```

## 5. Data Flow

### 5.1 Initial Ingest (one-time, days 1-4)

```
Config (sources + accounts)
    │
    ▼
For each source connector:
    list_changes(since=epoch_zero)        ← Composio: gdrive.list_files / onedrive.list_items / gmail.list_messages
        │
        ▼
    For each ChangeEvent:
        already in metadata with matching hash? → skip
        ──────────────────────────────────────────────
        fetch_content(doc_id)             ← Composio: gdrive.export_file / onedrive.download / gmail.get_attachment
            │
            ▼
        parser.parse(raw)                 ← pymupdf → pdfplumber → tesseract chain
            │
            ▼
        chunker.chunk(parsed)             ← SemanticSplitter, 512-token target
            │
            ▼
        embedder.embed_batch(chunks)      ← Ollama batch=32
            │
            ▼
        index.add_batch(ids, vectors)     ← TurboVec IdMapIndex
        metadata.upsert_document(...)
        metadata.upsert_chunks(...)
        │
        on any exception:
            dlq.write({doc_id, error, tb})
            metadata.mark_failed(doc_id)
            continue                       ← per-doc isolation
```

Throughput target on VPS: 30-50 chunks/sec sustained. Checkpoint every 1000 docs.

### 5.2 Nightly Delta

Same pipeline but `since=last_successful_run_at`. Drive uses `changes.list(pageToken)`, OneDrive uses `delta()`, Gmail uses `history.list(startHistoryId)`, localfs uses mtime walk. Deletions flow through: `metadata.mark_deleted(doc_id)` → `index.delete_by_doc_id(doc_id)`. Typical nightly diff: under 500 docs, 5-15 minutes.

### 5.3 Bundle Emission

```
/var/lib/rag/bundles/
├── pending/run-20260524T030000/
│   ├── index.tq
│   ├── meta.sqlite
│   └── manifest.json    ← {created_at, doc_count, chunk_count, index_sha256}
└── current → run-20260524T030000   # atomic symlink swap on success
```

### 5.4 Bundle Sync

Laptop `rag-sync` polls `current` via rsync `--link-dest` against prior version. Typical nightly transfer is the changed shards only (often under 500MB instead of 6-10GB). On finish: verify manifest `index_sha256`, atomic symlink swap in the laptop-side `current`, reload `rag-server`.

### 5.5 Query Path

```
User question
    │
    ▼
embedder.embed_query(text)            ← same BGE-small model, same vector space
    │
    ▼
index.search(qvec, k=20)              ← TurboVec returns chunk_ids + scores
    │
    ▼
metadata.hydrate_chunks(chunk_ids)    ← attach source_url, page, text
    │
    ▼
reranker.rerank(query, chunks) → top 5  ← cross-encoder bge-reranker-base
    │
    ▼
llm.generate(prompt + context)        ← Claude CLI (default) | Ollama (if private:)
    │
    ▼
Answer + citations
```

Citations always link back to source: Drive URL, OneDrive web URL, Gmail message permalink, or local file path with page anchor.

## 6. Error Handling

Four isolation layers:

**Per-source.** If `gdrive` connector throws at `list_changes`, orchestrator logs it, marks source `last_run_status='failed'`, continues to next source. Auth failures surface as a Tailscale notification on the laptop ("re-auth GDrive account `personal-jeremy`").

**Per-document.** Try/except around the entire parse→chunk→embed→index sequence. On exception: full traceback + doc metadata to DLQ, mark document `status='failed'`, continue. Never `except: pass`.

**Per-batch (embedding).** Ollama can transiently OOM or stall on a malformed batch. Catch, retry once with `batch_size=1` to isolate the offending chunk, send that chunk to DLQ, continue.

**Per-run (orchestrator).** Wraps the whole nightly job. On unhandled exception: emit `state=crashed`, write last checkpoint to `runs.last_resumable_at`, exit non-zero. Next run resumes mid-source rather than from zero.

**Retry policy**

- Transient (HTTP 429/5xx, connection reset, Ollama timeout, **Tesseract OOM**, **pdf2image temp-dir contention**) → exponential backoff, max 3 retries, then DLQ.
- Auth (HTTP 401/403) → fail-fast for that source, notify, no retry.
- Permanent (corrupt PDF, password-protected without supplied key, unsupported MIME, file size > 100MB) → straight to DLQ, no retry.

**DLQ replay.** `rag dlq replay [--source X] [--max-age 7d]`. Critical for the OCR path where Tesseract sometimes fails first attempt due to memory pressure but succeeds on second.

**Index corruption.** Manifest includes SHA-256 of `index.tq`. Laptop sync verifies before atomic swap. On mismatch: refuse to swap, alert, keep prior bundle active.

**Re-auth flow.** Composio connections expire. When detected, write `auth_needed.json` to bundle dir + Tailscale notification. Re-auth happens in Cowork via Composio's auth-link flow; orchestrator picks up on next run.

## 7. Testing

Three test tiers, all in `tests/`:

**Unit (fast, hermetic, every commit).** Each component in isolation with fakes. Parser against a fixture library (text PDF, scanned PDF, DOCX, PPTX, corrupt file, encrypted PDF). Chunker for deterministic chunking. Embedder mocked. Metadata against in-memory SQLite. Index with synthetic vectors. Target: under 10s suite.

**Integration (medium, real services).** `tests/integration/` runs against a dedicated test Google Drive folder, OneDrive folder, and Gmail label, each pre-loaded with known docs. Validates the full Composio→parse→chunk→embed→index→search loop. Gated behind `RAG_INTEGRATION=1`. Asserts: "ingest folder X; search query Y returns chunk Z at rank ≤3."

**Eval (slow, quality-focused).** `tests/eval/` — 30 QA pairs with known correct source docs. Measures recall@5 and answer faithfulness (LLM-as-judge via Claude). Run before releasing config changes. Tracks regressions in `eval-history.jsonl`.

**Smoke tests in production.** Orchestrator starts every nightly run with a self-check — ingest a known fixture doc, query for it, confirm rank-1. Fails the run if smoke fails.

**Verification gate.** No feature `passes=true` in `.agent/tasks.json` until: (a) unit tests pass, (b) integration tests pass against real Composio, (c) a fixture corpus demonstrates a correct answer with correct citations.

## 8. Configuration

`config.yaml` shape:

```yaml
sources:
  - kind: gdrive
    accounts: [personal-jeremy, work-dobeu, work-baldor]
    include_paths: ["/", "Shared drives/"]
    mime_filter: [application/pdf, application/vnd.google-apps.document, application/vnd.openxmlformats-officedocument.wordprocessingml.document]
  - kind: onedrive
    accounts: [personal, work-baldor]
  - kind: gmail
    accounts: [jswilliamstu@gmail.com]
    attachment_only: true
    mime_filter: [application/pdf]
  - kind: outlook
    accounts: [work-baldor]
    attachment_only: true
  - kind: localfs
    # Paths are resolved on the host running the orchestrator (the VPS).
    # To index laptop folders, mirror them to the VPS first via Syncthing
    # or rclone bisync; the VPS-side mirror path is what goes here.
    paths:
      - /var/lib/rag/mirrors/laptop/Documents
      - /var/lib/rag/mirrors/laptop/Downloads-archive
    laptop_mirror:
      tool: syncthing         # syncthing | rclone-bisync
      direction: one_way      # laptop → VPS only; VPS never writes back

embedding:
  model: bge-small-en-v1.5
  ollama_url: http://localhost:11434
  batch_size: 32

chunking:
  primary: semantic
  fallback_size: 512
  overlap: 64

ocr:
  enabled: true
  strategy: auto_detect       # auto_detect | always | never
  min_chars_per_page: 100

llm:
  default: claude-cli
  # If a query begins with the literal prefix `private:` (or carries
  # `private=true` in the MCP tool call), generation routes to Ollama
  # and the chunks never leave the laptop.
  private_prefix: "private:"
  private_tag_routes_to: ollama
  ollama_model: qwen2.5:7b

paths:
  bundle_dir: /var/lib/rag/bundles
  dlq: /var/lib/rag/dlq.jsonl
  metadata: /var/lib/rag/meta.sqlite
```

## 9. Security and Privacy

- All cloud-source auth is held by Composio, not stored in repo.
- The VPS holds copies of indexed content via the metadata sidecar (chunk text). The metadata DB is encrypted at rest using filesystem-level encryption (LUKS on VPS).
- The bundle sync uses Tailscale's WireGuard — no public ports on the VPS.
- Queries tagged `private:` never leave the laptop — embedding and generation both run locally on Ollama.
- The Claude Code CLI uses the user's Max subscription; query context is sent to Anthropic per Claude's terms.
- The user can rotate any source's auth via Composio at any time without re-ingest.

## 10. Open Questions

- **VPS provider:** Hetzner CPX31 (8 vCPU / 16GB / 240GB NVMe / ~€15/mo) vs DigitalOcean Premium AMD 8GB. The spec is provider-agnostic but install scripts will target Ubuntu 24.04 LTS.
- **Reranker placement:** Cross-encoder on laptop CPU may add 100-300ms per query. If unacceptable we drop it; recall@20 from TurboVec alone is likely sufficient.
- **Initial ingest scheduling:** Run continuously day 1-4, or spread over a week to avoid Composio rate-limits. Decide during first 10K-doc dry run.
- **Laptop mirror tool:** Syncthing (free, peer-to-peer, friendly UI) vs `rclone bisync` (one-shot, scriptable). Defaulting to Syncthing in this spec — revisit if Windows ACL behaviour proves problematic.

## 11. Out of Scope (Phase 2+)

- Webhook-driven near-real-time sync.
- Additional sources: Notion, Dropbox, Box, Confluence, Slack threads.
- Multi-user / RBAC.
- Local web chat UI (CLI + MCP cover Phase 1).
- Re-ranking using LLM-based pointwise scorer.
- Cost tracking dashboard.

## 12. Approval Trail

- 2026-05-23: Sections 1-2 approved by Jeremy.
- 2026-05-23: Sections 3-5 approved by Jeremy.
- 2026-05-23: Full design approved, spec written, awaiting final review before transition to writing-plans.
