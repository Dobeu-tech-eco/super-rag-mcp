from __future__ import annotations

from pathlib import Path

import pytest

import rag.serve.mcp_server as mod


class _FakeMeta:
    def list_runs(self):
        return []


class _FakeDLQ:
    def __init__(self, path: Path) -> None:
        self.path = path

    def iter_entries(self):
        return iter(())


@pytest.mark.asyncio
async def test_build_app_registers_four_tools(tmp_path, monkeypatch):
    dlq = _FakeDLQ(tmp_path / "dlq.jsonl")

    def _fake_build(_cfg_path):
        return (object(), _FakeMeta(), dlq, object(), object())

    monkeypatch.setattr(mod, "_build", _fake_build)
    app = mod.build_app(Path("config.yaml"))
    tools = await app.list_tools()
    names = {t.name for t in tools}
    assert {"rag_query", "rag_sync", "rag_status", "rag_dlq_list"} <= names
    status_tool = next(t for t in tools if t.name == "rag_status")
    assert status_tool.annotations is not None
    assert status_tool.annotations.readOnlyHint is True
    sync_tool = next(t for t in tools if t.name == "rag_sync")
    assert sync_tool.annotations.readOnlyHint is False


@pytest.mark.asyncio
async def test_read_only_http_app_constructs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        mod, "_build",
        lambda _: (object(), _FakeMeta(), _FakeDLQ(tmp_path / "dlq.jsonl"), object(), object()),
    )
    app = mod.build_app(Path("config.yaml"), allow_sync=False)
    assert {t.name for t in await app.list_tools()} == {
        "rag_query", "rag_status", "rag_dlq_list",
    }
    assert callable(app.streamable_http_app())
