# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
