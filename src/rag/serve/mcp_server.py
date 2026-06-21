# src/rag/serve/mcp_server.py
"""MCP server exposing the RAG pipeline as tools (rag_query/sync/status/dlq_list).

Pure handler functions take injected dependencies so they unit-test with fakes;
``mcp`` is an optional, lazy-imported dependency (see build_app / main below).
Return types are TypedDicts so FastMCP can emit a structured outputSchema.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

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


def run_query(engine: "QueryEngine", question: str) -> QueryResult:
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


def run_status(meta: "MetadataStore", dlq: "DeadLetterQueue") -> StatusResult:
    """Summarize last run + DLQ depth (mirrors `rag status`)."""
    runs = meta.list_runs()
    try:
        dlq_count = sum(
            1
            for line in dlq.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except FileNotFoundError:
        dlq_count = 0
    return {
        "total_runs": len(runs),
        "last_run": runs[0] if runs else None,
        "dlq_entries": dlq_count,
    }


def run_dlq_list(dlq: "DeadLetterQueue", limit: int = 50) -> list[dict[str, Any]]:
    """Return up to ``limit`` dead-letter entries."""
    out: list[dict[str, Any]] = []
    for entry in dlq.iter_entries():
        if len(out) >= limit:
            break
        out.append(entry)
    return out
