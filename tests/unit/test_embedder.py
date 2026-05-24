import httpx
import pytest
import respx
from rag.embedder import OllamaEmbedder


@respx.mock
def test_embed_query():
    respx.post("http://localhost:11434/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})
    )
    e = OllamaEmbedder(model="bge-small-en-v1.5", base_url="http://localhost:11434")
    v = e.embed_query("hello")
    assert v == [0.1, 0.2, 0.3]


@respx.mock
def test_embed_batch_returns_one_vector_per_text():
    respx.post("http://localhost:11434/api/embeddings").mock(
        side_effect=lambda req: httpx.Response(200, json={"embedding": [0.5, 0.5, 0.5]})
    )
    e = OllamaEmbedder(model="bge-small-en-v1.5", base_url="http://localhost:11434", batch_size=2)
    vectors = e.embed_batch(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 3 for v in vectors)


@respx.mock
def test_embed_propagates_http_errors():
    respx.post("http://localhost:11434/api/embeddings").mock(
        return_value=httpx.Response(500, text="boom")
    )
    e = OllamaEmbedder(model="bge-small-en-v1.5", base_url="http://localhost:11434")
    with pytest.raises(httpx.HTTPStatusError):
        e.embed_query("hello")
