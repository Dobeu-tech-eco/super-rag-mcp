# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-06-21

### Added
- **Bearer-token auth for the HTTP MCP transport.** `--transport streamable-http` now
  requires `RAG_MCP_TOKEN` and refuses to start without it (fail-closed); requests must send
  `Authorization: Bearer <token>`. Implemented as pure-ASGI middleware so the streaming
  response is preserved (`src/rag/serve/_http_auth.py`).
- **Read-only-by-default remote surface.** Over HTTP only `rag_query`/`rag_status`/`rag_dlq_list`
  are exposed; set `RAG_MCP_ALLOW_SYNC=1` to also expose the `rag_sync` write tool.
- Tunnel quickstart in `docs/mcp-server.md` (cloudflared/ngrok) for a public URL while keeping
  generation — and the corpus — local.

### Fixed
- **`rag sync --full` / `rag_sync(full=True)`:** re-index from scratch by ignoring the last
  successful run watermark (`SyncOrchestrator.run(full=…)`).
- **Concurrency:** `rag_query` no longer mutates a shared `QueryEngine` (`eng.top_k = …`);
  `top_k` is threaded per call and tool execution is serialized with a lock so a query can't
  read the index mid-sync. `QueryEngine.ask` gained a backward-compatible `top_k` parameter.

### Changed
- Default HTTP bind documented as `127.0.0.1` (use a tunnel/proxy), not `0.0.0.0`.
- `__version__` synced to the packaged version (was stale at `0.1.0`).

## [0.2.0] - 2026-06-21

### Added
- **MCP server (`rag-mcp`)** exposing the RAG pipeline as MCP tools for Hermes,
  Cursor, and other MCP clients, with a new optional `[mcp]` extra (`mcp >= 1.2`,
  lazy-imported) and a `rag-mcp` console script.
- Four MCP tools: `rag_query`, `rag_sync`, `rag_status`, `rag_dlq_list`, annotated
  with read-only / write hints and returning structured TypedDict output.
- Optional `streamable-http` transport (`--transport/--host/--port`) for remote
  hosting; stdio remains the default for local, private use.
- `Dockerfile` + `.dockerignore` for running the HTTP MCP server in a container
  (`COMPOSIO_API_KEY` stays a runtime env var).
- Ona/Gitpod dev environment: `.gitpod.yml` and `.devcontainer/devcontainer.json`.
- Documentation: `docs/mcp-server.md` (tools, client wiring, HTTP/Docker, cloud dev)
  and a README "MCP server" section.

## [0.1.0]

### Added
- Phase 1 local-files RAG pipeline (parse, OCR fallback, chunk, embed, index, query)
  with Claude CLI + Ollama backends.
- Phase 2 cloud connectors (Google Drive, OneDrive, Gmail, Outlook) over Composio.
