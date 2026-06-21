from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_mcp_extra_declared():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert "mcp" in extras
    assert any(dep.startswith("mcp>=") for dep in extras["mcp"])


def test_rag_mcp_script_declared():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    assert scripts.get("rag-mcp") == "rag.serve.mcp_server:main"
