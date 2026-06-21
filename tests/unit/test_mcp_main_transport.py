from __future__ import annotations

import rag.serve.mcp_server as mod


class _FakeApp:
    def __init__(self) -> None:
        self.settings = type("S", (), {})()
        self.ran_with: str | None = None

    def run(self, transport: str = "stdio") -> None:
        self.ran_with = transport


def test_main_supports_http_transport(monkeypatch):
    fake = _FakeApp()
    monkeypatch.setattr(mod, "build_app", lambda p: fake)
    mod.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000"])
    assert fake.ran_with == "streamable-http"
    assert fake.settings.host == "0.0.0.0"
    assert fake.settings.port == 9000


def test_main_defaults_to_stdio(monkeypatch):
    fake = _FakeApp()
    monkeypatch.setattr(mod, "build_app", lambda p: fake)
    mod.main([])
    assert fake.ran_with == "stdio"
