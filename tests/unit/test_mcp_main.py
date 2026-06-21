from __future__ import annotations

from pathlib import Path

import rag.serve.mcp_server as mod


class _FakeApp:
    def __init__(self) -> None:
        self.ran_with: str | None = None

    def run(self, transport: str = "stdio") -> None:
        self.ran_with = transport


def test_main_builds_app_with_config_and_runs_stdio(monkeypatch):
    captured = {}
    fake = _FakeApp()

    def _fake_build_app(cfg_path: Path):
        captured["cfg"] = cfg_path
        return fake

    monkeypatch.setattr(mod, "build_app", _fake_build_app)
    mod.main(["--config", "custom.yaml"])
    assert captured["cfg"] == Path("custom.yaml")
    assert fake.ran_with == "stdio"


def test_main_uses_rag_config_env_default(monkeypatch):
    captured = {}
    monkeypatch.setenv("RAG_CONFIG", "from_env.yaml")

    def _capture(cfg_path: Path):
        captured["cfg"] = cfg_path
        return _FakeApp()

    monkeypatch.setattr(mod, "build_app", _capture)
    mod.main([])
    assert captured["cfg"] == Path("from_env.yaml")
