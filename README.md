# Super RAG — Drive + OneDrive + Email + Local

Self-hosted retrieval-augmented generation over your personal cloud and local documents.

## Status

**Released in v0.3.0 and earlier.** The local pipeline ingests PDFs, DOCX, TXT, and Markdown with OCR fallback, semantic chunking, Ollama embeddings, a TurboVec index, and Claude Code CLI or Ollama generation. Optional Composio connectors add Google Drive, OneDrive, Gmail attachments, and Outlook attachments. The optional MCP server supports stdio and bearer-authenticated HTTP, with HTTP write access disabled by default. v0.3.0 also added `rag sync --full` and fixed concurrent MCP queries sharing `top_k`. See the [changelog](CHANGELOG.md) for release history.

**Verification.** Earlier project records describe live Composio contract checks against Google Drive and Outlook. The November 17, 2026 baseline covers local unit and lint checks on v0.3.0 plus the exporter and Dependabot commits. The [verification receipt](.harness/receipt.md) records exact results and coverage limits. Section 7 of the [setup guide](docs/SETUP.md) covers cloud setup.

The potential fold of `dobeu-knowledge-pilot` into Super RAG is future work that requires separate approval.

## Quickstart (live)

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
cp config.example.yaml config.yaml   # edit paths/sources
rag sync                              # ingest configured roots
rag sync --full                       # scan without the last successful run watermark
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

**Sync path.** `rag sync` walks each configured `Connector` (`LocalfsConnector` plus the Composio-backed `GdriveConnector`, `OneDriveConnector`, `GmailConnector`, `OutlookConnector`) for change events since the last successful run. The pipeline fetches new or modified documents as `RawDoc`, parses them, uses LlamaIndex to produce sentence-aware chunks with page ranges, and embeds the chunks in batches through Ollama. It updates the TurboVec `VectorIndex` and SQLite `MetadataStore`. Per-document processing failures land in a JSONL `DeadLetterQueue`. Connector manifests make deletes observable across runs.

**Query path.** `rag query` strips the optional `private:` prefix, embeds the question with the same Ollama model used at ingest, runs a top-k search against the vector index, hydrates the resulting chunk IDs from SQLite to get text + source URLs + page numbers, and hands a prompt with citations to the routed `LLMBackend` (Claude CLI by default, Ollama when `private:` was used). The CLI renders the answer plus a citations table.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for components, data contracts, and extension points, and [docs/CODEMAPS/rag.md](docs/CODEMAPS/rag.md) for a file-by-file navigation aid.

## Docs

- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Codemap: [docs/CODEMAPS/rag.md](docs/CODEMAPS/rag.md)
- Design spec: `docs/superpowers/specs/2026-05-23-rag-pipeline-design.md`
- MVP plan: `docs/superpowers/plans/2026-05-23-rag-mvp-plan.md`
