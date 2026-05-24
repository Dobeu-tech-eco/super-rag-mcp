"""Ollama-backed embedder. One interface, used identically on ingest and query sides."""
from __future__ import annotations
import httpx


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 batch_size: int = 32, timeout: float = 60.0) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def embed_query(self, text: str) -> list[float]:
        resp = self._client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama embeddings endpoint is one-text-per-call.
        # Batch here means how many we issue before yielding control.
        out: list[list[float]] = []
        for chunk_start in range(0, len(texts), self.batch_size):
            for t in texts[chunk_start:chunk_start + self.batch_size]:
                out.append(self.embed_query(t))
        return out
