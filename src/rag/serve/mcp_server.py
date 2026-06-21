# src/rag/serve/mcp_server.py
"""MCP server exposing the RAG pipeline as tools (rag_query/sync/status/dlq_list).

Pure handler functions take injected dependencies so they unit-test with fakes;
``mcp`` is an optional, lazy-imported dependency (see build_app / main below).
Return types are TypedDicts so FastMCP can emit a structured outputSchema.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

from rag.serve.cli import _build, _build_connectors

if TYPE_CHECKING:
    from rag.dlq import DeadLetterQueue
    from rag.metadata import MetadataStore
    from rag.query import QueryEngine


class CitationDict(TypedDict):
    chunk_id: str
    source_url: str
    excerpt: str
    page: int | None
    score: float


class QueryResult(TypedDict):
    answer: str
    private: bool
    citations: list[CitationDict]


class StatusResult(TypedDict):
    total_runs: int
    last_run: dict[str, Any] | None
    dlq_entries: int


def actionable_hint(exc: Exception) -> str | None:
    """Map a known failure to a next-step hint, or None if unrecognized."""
    msg = str(exc).lower()
    if "11434" in msg or "ollama" in msg:
        return (
            "Ollama is not reachable. Start it with `ollama serve` and confirm "
            "the embedding/LLM models are pulled (see config.example.yaml)."
        )
    if "config" in msg or isinstance(exc, FileNotFoundError):
        return "config.yaml not found. Pass --config or set RAG_CONFIG to a valid path."
    if "composio_api_key" in msg or "composio" in msg:
        return "Cloud sync needs COMPOSIO_API_KEY exported and a composio: config block."
    return None


def run_query(engine: QueryEngine, question: str) -> QueryResult:
    """Embed -> retrieve -> generate, returning a JSON-serializable answer."""
    ans = engine.ask(question)
    return {
        "answer": ans.text,
        "private": ans.private,
        "citations": [
            {
                "chunk_id": c.chunk_id,
                "source_url": c.source_url,
                "excerpt": c.excerpt,
                "page": c.page,
                "score": c.score,
            }
            for c in ans.citations
        ],
    }


def run_status(meta: MetadataStore, dlq: DeadLetterQueue) -> StatusResult:
    """Summarize last run + DLQ depth (mirrors `rag status`)."""
    runs = meta.list_runs()
    try:
        dlq_count = sum(
            1 for line in dlq.path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    except FileNotFoundError:
        dlq_count = 0
    return {
        "total_runs": len(runs),
        "last_run": runs[0] if runs else None,
        "dlq_entries": dlq_count,
    }


def run_dlq_list(dlq: DeadLetterQueue, limit: int = 50) -> list[dict[str, Any]]:
    """Return up to ``limit`` dead-letter entries."""
    out: list[dict[str, Any]] = []
    for entry in dlq.iter_entries():
        if len(out) >= limit:
            break
        out.append(entry)
    return out


class SyncResult(TypedDict):
    docs_processed: int
    docs_failed: int
    chunks_indexed: int


def run_sync(orch: Any, index: Any, *, full: bool = False) -> SyncResult:
    """Run a sync pass; persist the vector index even if the run raises."""
    try:
        result = orch.run(full=full)
    finally:
        index.save()
    return {
        "docs_processed": result.docs_processed,
        "docs_failed": result.docs_failed,
        "chunks_indexed": result.chunks_indexed,
    }


def build_app(cfg_path: Path):
    """Construct the FastMCP app, wiring tools to the RAG pipeline.

    ``mcp`` is imported here (not at module top) so the package stays optional.
    """
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    from rag.llm import ClaudeCLIBackend, OllamaBackend
    from rag.query import QueryEngine
    from rag.sync import SyncOrchestrator

    cfg, meta, dlq, index, embedder = _build(cfg_path)
    app = FastMCP("super-rag")
    _engine: dict[str, QueryEngine] = {}

    def _reraise(exc: Exception) -> Exception:
        hint = actionable_hint(exc)
        return RuntimeError(f"{exc} — {hint}") if hint else exc

    def _query_engine() -> QueryEngine:
        if "e" not in _engine:
            _engine["e"] = QueryEngine(
                embedder=embedder,
                index=index,
                metadata=meta,
                claude=ClaudeCLIBackend(),
                ollama=OllamaBackend(model=cfg.llm.ollama_model, base_url=cfg.embedding.ollama_url),
                top_k=5,
                private_prefix=cfg.llm.private_prefix,
                default_backend=cfg.llm.default,
                private_routes_to=cfg.llm.private_tag_routes_to,
            )
        return _engine["e"]

    _READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
    _WRITE = ToolAnnotations(readOnlyHint=False, idempotentHint=False, openWorldHint=True)

    @app.tool(annotations=_READ)
    def rag_query(question: str, top_k: int = 5) -> QueryResult:
        """Ask the indexed corpus a question. Prefix with the configured private
        prefix (default 'private:') to force local-only generation."""
        try:
            eng = _query_engine()
            # single cached engine; top_k mutation is safe under stdio (single-threaded)
            eng.top_k = top_k
            return run_query(eng, question)
        except Exception as exc:
            raise _reraise(exc) from exc

    @app.tool(annotations=_WRITE)
    def rag_sync(full: bool = False) -> SyncResult:
        """Ingest deltas from all configured sources. full=True reindexes from scratch."""
        try:
            connectors, accounts = _build_connectors(cfg)
            orch = SyncOrchestrator(
                connectors=connectors,
                accounts_per_connector=accounts,
                embedder=embedder,
                index=index,
                metadata=meta,
                dlq=dlq,
                chunk_size=cfg.chunking.fallback_size,
                overlap=cfg.chunking.overlap,
                ocr_strategy=cfg.ocr.strategy if cfg.ocr.enabled else "never",
            )
            return run_sync(orch, index, full=full)
        except Exception as exc:
            raise _reraise(exc) from exc

    @app.tool(annotations=_READ)
    def rag_status() -> StatusResult:
        """Last-run summary and dead-letter-queue depth."""
        return run_status(meta, dlq)

    @app.tool(annotations=_READ)
    def rag_dlq_list(limit: int = 50) -> list[dict]:
        """List up to ``limit`` dead-letter entries."""
        return run_dlq_list(dlq, limit)

    return app


def main(argv: list[str] | None = None) -> None:
    """Console entry point (`rag-mcp`).

    Default ``stdio`` transport keeps the server local and private. Pass
    ``--transport streamable-http`` (with optional ``--host``/``--port``) to serve
    remotely — note the index and embeddings then leave the local machine.
    """
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="rag-mcp", description="Super-RAG MCP server")
    parser.add_argument(
        "--config",
        "-c",
        default=os.environ.get("RAG_CONFIG", "config.yaml"),
        help="Path to config.yaml (or set RAG_CONFIG).",
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "streamable-http"],
        help="MCP transport (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host for streamable-http transport.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port for streamable-http transport.",
    )
    args = parser.parse_args(argv)
    app = build_app(Path(args.config))
    if args.transport == "streamable-http":
        app.settings.host = args.host
        app.settings.port = args.port
    app.run(transport=args.transport)


if __name__ == "__main__":
    main()
