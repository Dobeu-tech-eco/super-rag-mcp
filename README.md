# Super RAG — Drive + OneDrive + Email + Local

Self-hosted retrieval-augmented generation over your personal cloud and local documents.

## Status

**Phase 1 (Local-files MVP): shipped.** End-to-end pipeline works against PDFs, DOCX, TXT, and Markdown on the local filesystem with OCR fallback, semantic chunking, Ollama embeddings, a turbovec vector index, and dual LLM backends (Claude Code CLI + local Ollama). Tasks 1–15 of the MVP plan are merged; unit + integration suites are green.

**Phase 2 (Cloud connectors): wired.** Google Drive, OneDrive, Gmail (attachments), and Outlook (attachments) are implemented over Composio and wired into `rag sync`. The Composio request/response contract (action names, params, and the presigned-`s3url` download model) is validated against the live API for Drive and Outlook; install with the `cloud` extra and configure accounts per [docs/SETUP.md](docs/SETUP.md) §7.

## Quickstart (live)

```bash
uv venv && uv pip install -e ".[dev]"
cp config.example.yaml config.yaml   # edit paths/sources
rag sync                              # ingest configured roots
rag query "what does the safety policy say about new drivers?"
rag status                            # last run + DLQ counts
rag dlq list                          # inspect failed documents
```

Use `private: ...` as a query prefix to keep generation on the local Ollama backend.

## MCP server

The pipeline is also exposed as an MCP server (`rag-mcp`) so Hermes, Cursor, and other
MCP clients can drive it. Install the optional `[mcp]` extra and run over stdio:

```bash
uv pip install -e ".[mcp]"
rag-mcp -c config.yaml                 # stdio (local, private) — default
```

Four tools are registered: `rag_query`, `rag_sync`, `rag_status`, `rag_dlq_list`. For a
remote URL, set `RAG_MCP_TOKEN` and run
`rag-mcp --transport streamable-http --host 127.0.0.1 --port 8000`, then expose it through a
tunnel (cloudflared/ngrok). The HTTP transport requires the bearer token and is read-only by
default (`rag_sync` needs `RAG_MCP_ALLOW_SYNC=1`). See
[docs/mcp-server.md](docs/mcp-server.md) for tool schemas, client wiring, the tunnel/Docker
path, and the Ona/Gitpod dev environment.

## Prerequisites

- Python 3.12
- Ollama running locally with `bge-small-en-v1.5` (embeddings, 384-dim) and `qwen2.5:7b` (private generation) pulled
- Tesseract + Poppler installed (only needed for scanned-PDF OCR)
- Claude Code CLI installed and authenticated (used as the default generator)

## Architecture at a glance

**Sync path.** `rag sync` walks each configured `Connector` (`LocalfsConnector` plus the Composio-backed `GdriveConnector`, `OneDriveConnector`, `GmailConnector`, `OutlookConnector`) for change events since the last successful run. New/modified docs are fetched as `RawDoc`, parsed (PyMuPDF for PDFs with auto-detect OCR fallback, python-docx for DOCX, plain decode for text), chunked sentence-aware via LlamaIndex with per-chunk page-range mapping, embedded in batch through Ollama, and written atomically into the turbovec `VectorIndex` and SQLite `MetadataStore`. Failures land in a JSONL `DeadLetterQueue`; the manifest in each local root makes deletes observable across runs.

**Query path.** `rag query` strips the optional `private:` prefix, embeds the question with the same Ollama model used at ingest, runs a top-k search against the vector index, hydrates the resulting chunk IDs from SQLite to get text + source URLs + page numbers, and hands a prompt with citations to the routed `LLMBackend` (Claude CLI by default, Ollama when `private:` was used). The CLI renders the answer plus a citations table.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for components, data contracts, and extension points, and [docs/CODEMAPS/rag.md](docs/CODEMAPS/rag.md) for a file-by-file navigation aid.

## Docs

- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Codemap: [docs/CODEMAPS/rag.md](docs/CODEMAPS/rag.md)
- Design spec: `docs/superpowers/specs/2026-05-23-rag-pipeline-design.md`
- MVP plan: `docs/superpowers/plans/2026-05-23-rag-mvp-plan.md`
