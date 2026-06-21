"""Query engine: embed -> retrieve -> hydrate -> generate."""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np

from rag.llm import LLMBackend, route_query
from rag.types import Answer, Citation

if TYPE_CHECKING:
    from rag.embedder import OllamaEmbedder
    from rag.index import VectorIndex
    from rag.metadata import MetadataStore

_SYSTEM_PROMPT = (
    "You are an expert assistant. Answer the question using only the supplied context. "
    "Cite specific passages by quoting brief excerpts. If the answer is not in the context, "
    "say so plainly — do not invent. Be concise."
)


class QueryEngine:
    def __init__(
        self,
        embedder: "OllamaEmbedder",
        index: "VectorIndex",
        metadata: "MetadataStore",
        claude: LLMBackend,
        ollama: LLMBackend,
        top_k: int = 5,
        private_prefix: str = "private:",
        default_backend: Literal["claude-cli", "ollama"] = "claude-cli",
        private_routes_to: Literal["claude-cli", "ollama"] = "ollama",
    ) -> None:
        self.embedder = embedder
        self.index = index
        self.metadata = metadata
        self.claude = claude
        self.ollama = ollama
        self.top_k = top_k
        self.private_prefix = private_prefix
        self.default_backend = default_backend
        self.private_routes_to = private_routes_to

    def ask(self, question: str, top_k: int | None = None) -> Answer:
        cleaned, is_private = route_query(
            question, claude=self.claude, ollama=self.ollama,
            private_prefix=self.private_prefix,
            default=self.default_backend,
            private_routes_to=self.private_routes_to,
        )

        k = self.top_k if top_k is None else top_k
        qvec = np.array(self.embedder.embed_query(cleaned), dtype=np.float32)
        hits = self.index.search(qvec, k=k)
        chunk_ids = [h[0] for h in hits]
        score_by_id = {h[0]: h[1] for h in hits}

        rows = self.metadata.hydrate_chunks(chunk_ids)
        # Preserve ranking order.
        by_id = {r["chunk_id"]: r for r in rows}
        ordered = [by_id[cid] for cid in chunk_ids if cid in by_id]

        citations = [
            Citation(
                chunk_id=r["chunk_id"],
                source_url=r["source_url"],
                excerpt=r["text"][:200],
                page=r.get("page_start"),
                score=score_by_id.get(r["chunk_id"], 0.0),
            )
            for r in ordered
        ]

        context = "\n\n".join(
            f"[Source: {r['source_url']} page {r.get('page_start')}]\n{r['text']}"
            for r in ordered
        )
        user_msg = f"Context:\n{context}\n\nQuestion: {cleaned}"

        backend: LLMBackend = (
            self.ollama if (is_private and self.private_routes_to == "ollama")
            else self.claude if self.default_backend == "claude-cli"
            else self.ollama
        )
        answer_text = backend.generate(system=_SYSTEM_PROMPT, user=user_msg)
        return Answer(text=answer_text, citations=citations, private=is_private)
