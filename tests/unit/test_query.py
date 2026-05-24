from unittest.mock import MagicMock
import numpy as np
from rag.query import QueryEngine
from rag.types import Answer


def test_query_returns_answer_with_citations():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]
    index = MagicMock()
    index.search.return_value = [
        ("localfs:default:doc1:00000", 0.95),
        ("localfs:default:doc2:00000", 0.80),
    ]
    metadata = MagicMock()
    metadata.hydrate_chunks.return_value = [
        {"chunk_id": "localfs:default:doc1:00000", "text": "Safety policy chunk A",
         "source_url": "file:///doc1.pdf", "page_start": 1, "page_end": 1},
        {"chunk_id": "localfs:default:doc2:00000", "text": "Safety policy chunk B",
         "source_url": "file:///doc2.pdf", "page_start": 3, "page_end": 3},
    ]
    claude = MagicMock(); claude.generate.return_value = "Drivers under 6 months..."
    ollama = MagicMock()

    qe = QueryEngine(embedder=embedder, index=index, metadata=metadata,
                     claude=claude, ollama=ollama, top_k=5,
                     private_prefix="private:", default_backend="claude-cli",
                     private_routes_to="ollama")
    answer = qe.ask("What does the safety policy say about new drivers?")
    assert isinstance(answer, Answer)
    assert "Drivers under 6 months" in answer.text
    assert len(answer.citations) == 2
    assert answer.citations[0].source_url == "file:///doc1.pdf"
    assert answer.citations[0].page == 1
    assert answer.private is False


def test_query_private_uses_ollama():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]
    index = MagicMock()
    index.search.return_value = [("localfs:default:doc1:00000", 0.9)]
    metadata = MagicMock()
    metadata.hydrate_chunks.return_value = [{
        "chunk_id": "localfs:default:doc1:00000", "text": "T",
        "source_url": "file:///x", "page_start": 1, "page_end": 1
    }]
    claude = MagicMock()
    ollama = MagicMock(); ollama.generate.return_value = "Local answer."

    qe = QueryEngine(embedder=embedder, index=index, metadata=metadata,
                     claude=claude, ollama=ollama, top_k=5,
                     private_prefix="private:", default_backend="claude-cli",
                     private_routes_to="ollama")
    answer = qe.ask("private: secret question")
    assert answer.text == "Local answer."
    assert answer.private is True
    claude.generate.assert_not_called()
