from __future__ import annotations

from dataclasses import dataclass

import pytest

from rag.serve.mcp_server import run_sync


@dataclass
class _Result:
    docs_processed: int
    docs_failed: int
    chunks_indexed: int


class _FakeOrch:
    def __init__(self, result=None, exc=None) -> None:
        self._result = result
        self._exc = exc
        self.full_seen: bool | None = None

    def run(self, full: bool = False):
        self.full_seen = full
        if self._exc:
            raise self._exc
        return self._result


class _FakeIndex:
    def __init__(self) -> None:
        self.saved = 0

    def save(self) -> None:
        self.saved += 1


def test_run_sync_returns_counts_and_saves_index():
    orch = _FakeOrch(result=_Result(3, 1, 12))
    index = _FakeIndex()
    out = run_sync(orch, index, full=True)
    assert out == {"docs_processed": 3, "docs_failed": 1, "chunks_indexed": 12}
    assert orch.full_seen is True
    assert index.saved == 1


def test_run_sync_saves_index_even_on_failure():
    orch = _FakeOrch(exc=RuntimeError("boom"))
    index = _FakeIndex()
    with pytest.raises(RuntimeError, match="boom"):
        run_sync(orch, index)
    assert index.saved == 1
