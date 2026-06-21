from __future__ import annotations

import json
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "hermes-mcp.json.example"


def test_example_registers_both_servers():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    servers = data["mcpServers"]
    assert "super-rag" in servers
    assert servers["super-rag"]["command"] == "rag-mcp"
    assert "composio-unified" in servers
    assert "url" in servers["composio-unified"]
