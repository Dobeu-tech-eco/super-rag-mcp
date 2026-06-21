from __future__ import annotations

import pytest
import uvicorn

import rag.serve.mcp_server as mod
from rag.serve._http_auth import BearerAuthMiddleware


class _FakeApp:
    def __init__(self) -> None:
        self.ran_with: str | None = None

    def run(self, transport: str = "stdio") -> None:
        self.ran_with = transport

    def streamable_http_app(self) -> str:
        return "ASGI_SENTINEL"


def test_main_defaults_to_stdio(monkeypatch):
    fake = _FakeApp()
    monkeypatch.setattr(mod, "build_app", lambda p: fake)
    mod.main([])
    assert fake.ran_with == "stdio"


def test_http_requires_token(monkeypatch):
    monkeypatch.delenv("RAG_MCP_TOKEN", raising=False)
    # Token is checked before build_app, so a missing token fails fast w/o config.
    monkeypatch.setattr(
        mod, "build_app", lambda *a, **k: pytest.fail("build_app must not run without a token")
    )
    with pytest.raises(SystemExit):
        mod.main(["--transport", "streamable-http"])


def test_http_wraps_app_with_bearer_auth_and_runs_uvicorn(monkeypatch):
    monkeypatch.setenv("RAG_MCP_TOKEN", "secret")
    monkeypatch.delenv("RAG_MCP_ALLOW_SYNC", raising=False)
    captured: dict = {}

    def _build(cfg_path, *, allow_sync=True):
        captured["allow_sync"] = allow_sync
        return _FakeApp()

    def _run(app, host=None, port=None, **kw):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(mod, "build_app", _build)
    monkeypatch.setattr(uvicorn, "run", _run)
    mod.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000"])

    assert isinstance(captured["app"], BearerAuthMiddleware)
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000
    assert captured["allow_sync"] is False  # read-only over HTTP by default


def test_http_allow_sync_env_enables_write_tool(monkeypatch):
    monkeypatch.setenv("RAG_MCP_TOKEN", "secret")
    monkeypatch.setenv("RAG_MCP_ALLOW_SYNC", "1")
    captured: dict = {}

    def _build(cfg_path, *, allow_sync=True):
        captured["allow_sync"] = allow_sync
        return _FakeApp()

    monkeypatch.setattr(mod, "build_app", _build)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)
    mod.main(["--transport", "streamable-http"])
    assert captured["allow_sync"] is True
