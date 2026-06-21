from __future__ import annotations

from pathlib import Path

from rag.serve.mcp_server import (
    actionable_hint,
    run_dlq_list,
    run_query,
    run_status,
)
from rag.types import Answer, Citation


class _FakeEngine:
    def __init__(self) -> None:
        self.top_k = 5
        self.asked: list[str] = []

    def ask(self, question: str) -> Answer:
        self.asked.append(question)
        return Answer(
            text="the answer",
            private=question.startswith("private:"),
            citations=[
                Citation(
                    chunk_id="localfs:default:doc1:00000",
                    source_url="file:///doc1.pdf",
                    excerpt="snippet",
                    page=3,
                    score=0.42,
                )
            ],
        )


class _FakeMeta:
    def __init__(self, runs: list[dict]) -> None:
        self._runs = runs

    def list_runs(self) -> list[dict]:
        return self._runs


class _FakeDLQ:
    def __init__(self, path: Path, entries: list[dict]) -> None:
        self.path = path
        self._entries = entries

    def iter_entries(self):
        yield from self._entries


def test_run_query_serializes_answer_and_citations():
    eng = _FakeEngine()
    out = run_query(eng, "what is x?")
    assert out["answer"] == "the answer"
    assert out["private"] is False
    assert out["citations"] == [
        {
            "chunk_id": "localfs:default:doc1:00000",
            "source_url": "file:///doc1.pdf",
            "excerpt": "snippet",
            "page": 3,
            "score": 0.42,
        }
    ]
    assert eng.asked == ["what is x?"]


def test_run_status_counts_runs_and_dlq(tmp_path):
    dlq_file = tmp_path / "dlq.jsonl"
    dlq_file.write_text('{"doc_id":"d"}\n\n{"doc_id":"e"}\n', encoding="utf-8")
    meta = _FakeMeta([{"status": "ok"}, {"status": "ok"}])
    dlq = _FakeDLQ(dlq_file, [])
    out = run_status(meta, dlq)
    assert out["total_runs"] == 2
    assert out["last_run"] == {"status": "ok"}
    assert out["dlq_entries"] == 2


def test_run_status_handles_missing_dlq_file_and_no_runs(tmp_path):
    meta = _FakeMeta([])
    dlq = _FakeDLQ(tmp_path / "missing.jsonl", [])
    out = run_status(meta, dlq)
    assert out == {"total_runs": 0, "last_run": None, "dlq_entries": 0}


def test_run_dlq_list_respects_limit(tmp_path):
    entries = [{"doc_id": f"d{i}"} for i in range(5)]
    dlq = _FakeDLQ(tmp_path / "dlq.jsonl", entries)
    assert run_dlq_list(dlq, limit=3) == entries[:3]


def test_actionable_hint_maps_known_failures():
    assert "ollama" in actionable_hint(ConnectionError("Max retries to localhost:11434")).lower()
    assert "config" in actionable_hint(FileNotFoundError("config.yaml")).lower()
    assert actionable_hint(ValueError("something unrelated")) is None
