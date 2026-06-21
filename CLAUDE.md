# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Self-hosted RAG (retrieval-augmented generation) over local files (Phase 1) — planned to extend to Google Drive, OneDrive, and email (Phases 2–4). Single-host Python 3.12 app: SQLite for metadata, TurboVec for vectors, Ollama for embeddings, Claude Code CLI for generation with an Ollama fallback for `private:`-tagged queries.

Plan progression lives in `docs/superpowers/plans/`; design spec in `docs/superpowers/specs/`. **Phase 1 is feature-complete through Task 15** (per `.agent/`). When adding cloud connectors, follow Plans 2–4.

## Common commands

Setup (one-time): `uv venv && uv pip install -e ".[dev]"`. Prereqs assumed installed: Ollama with `bge-small-en-v1.5` + `qwen2.5:7b` pulled, Tesseract, Poppler, and authenticated `claude` CLI.

```bash
# Run the CLI (installed as `rag` script via pyproject)
rag sync                            # ingest deltas from configured sources
rag query "your question"           # default backend = claude CLI
rag query "private: your question"  # routes to local Ollama instead
rag status                          # last-run summary + DLQ count
rag dlq list                        # inspect dead-letter entries

# Tests
pytest                              # unit tests only (default)
pytest tests/unit/test_chunker.py::test_name   # single test
pytest -m integration               # E2E (requires Ollama + claude CLI running)
pytest --cov                        # with coverage (branch, source=src/rag)

# Lint / format
ruff check .
ruff format .
```

`config.yaml` (copy from `config.example.yaml`) is required at the repo root for CLI commands; override with `-c <path>`.

## Architecture

The pipeline is a linear data flow assembled in `src/rag/serve/cli.py::_build` and orchestrated by `SyncOrchestrator` / `QueryEngine`. Components communicate only through the dataclasses in `src/rag/types.py` (`ChangeEvent`, `RawDoc`, `ParsedDoc`, `Chunk`, `Citation`, `Answer`) — keep new components on that contract.

**Sync path** (`sync.py`): for each configured `Connector`, walk `list_changes(account, since)` → fetch `RawDoc` → `parser.parse` (PDF via PyMuPDF/pdfplumber, OCR fallback via pdf2image+pytesseract when text density is low; DOCX via python-docx; TXT direct) → `chunker.chunk_document` (sentence splitter w/ fallback size+overlap) → `OllamaEmbedder` (batched HTTP to `/api/embeddings`) → `VectorIndex` (TurboVec wrapper persisted to `<bundle_dir>/index.tq`) → `MetadataStore` (SQLite via `sqlite-utils`). Per-source and per-doc failures are isolated and written to the JSONL `DeadLetterQueue`; deletes propagate via `index.delete_by_doc_id`.

**Query path** (`query.py`): `route_query` strips the `private:` prefix (configurable) and decides backend → `OllamaEmbedder.embed_one` → `VectorIndex.search(top_k)` → `MetadataStore` hydrates chunks back to text + `source_url` + page range → `LLMBackend.generate` (`ClaudeCLIBackend` shells out to `claude --print`; `OllamaBackend` POSTs `/api/chat`) → returns `Answer` with `Citation` list and `private` flag.

**Connector contract** (`connectors/__init__.py`): new sources implement the `Connector` Protocol (`list_changes`, `fetch`, account handling) and raise `ConnectorAuthError` for auth failures so the orchestrator can skip that account without aborting the run. `localfs.py` is the reference implementation. Register new kinds in `config.py` (pydantic-discriminated `sources:` union) and wire them into `cli._build`'s connector/account maps.

**Identifier convention:** `chunk_id = "{source}:{account}:{doc_id}:{idx:05d}"`. Keep this stable — `VectorIndex.delete_by_doc_id` and metadata lookups depend on it.

**Embedding dim is hard-coded** in `cli.py` as `_INDEX_DIM = 384` (matches `bge-small-en-v1.5`). Changing the embedding model requires updating this constant and rebuilding the index.

## Conventions specific to this repo

- Python 3.12, `from __future__ import annotations` at top of every module; type hints throughout.
- All filesystem paths in config and storage are absolute Windows paths in the example (`C:\Users\...`). The code uses `pathlib.Path` and is OS-neutral; tests must use `tmp_path`.
- Ruff: line length 100, rules `E F I B UP RUF`, `E501` ignored; `B011` allowed in tests.
- Tests in `tests/unit/` are the contract; `tests/integration/test_e2e.py` is gated by `-m integration` and requires real Ollama + `claude` CLI. Fixtures (sample PDFs/DOCX) live in `tests/fixtures/`.
- Session state for long-running agentic work is tracked in `.agent/` (`progress.md`, `tasks.json`, `state.json`) per the user's global checkpoint protocol — update these when checkpointing, do not delete.

**MCP server** (`src/rag/serve/mcp_server.py`): exposes the pipeline as MCP tools
(`rag_query`, `rag_sync`, `rag_status`, `rag_dlq_list`) via `FastMCP` over stdio. Tool
handlers delegate to pure functions (`run_query`/`run_status`/`run_dlq_list`/`run_sync`)
that are dependency-injected for unit testing; tools carry MCP annotations and return
`TypedDict`s for structured output. `mcp` is an optional `[mcp]` extra, lazy-imported in
`build_app`/`main`. Entry point: `rag-mcp` (see `docs/mcp-server.md`).
