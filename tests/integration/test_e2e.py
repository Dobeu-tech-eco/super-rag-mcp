"""End-to-end: ingest fixtures, query via the engine, verify citations.

Skipped unless RAG_INTEGRATION=1 is set, because it needs a running Ollama.
"""
import os
import shutil
from pathlib import Path
import pytest
import yaml
from click.testing import CliRunner
from rag.serve.cli import main as cli


pytestmark = pytest.mark.integration


@pytest.fixture
def e2e_workspace(tmp_path: Path):
    fixtures = Path(__file__).parent.parent / "fixtures" / "e2e"
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for f in fixtures.glob("*.pdf"):
        shutil.copy(f, corpus / f.name)
    cfg = {
        "sources": [{"kind": "localfs", "paths": [str(corpus)]}],
        "embedding": {"model": "bge-small-en-v1.5",
                       "ollama_url": "http://localhost:11434", "batch_size": 8},
        "chunking": {"primary": "sentence", "fallback_size": 512, "overlap": 64},
        "ocr": {"enabled": True, "strategy": "auto_detect", "min_chars_per_page": 100},
        "llm": {"default": "claude-cli", "private_prefix": "private:",
                 "private_tag_routes_to": "ollama", "ollama_model": "qwen2.5:7b"},
        "paths": {"bundle_dir": str(tmp_path / "bundles"),
                   "dlq": str(tmp_path / "dlq.jsonl"),
                   "metadata": str(tmp_path / "meta.sqlite")},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    (tmp_path / "bundles").mkdir(parents=True)
    return cfg_path, corpus


@pytest.mark.skipif(os.getenv("RAG_INTEGRATION") != "1",
                    reason="Set RAG_INTEGRATION=1 with Ollama running")
def test_sync_then_query(e2e_workspace):
    cfg_path, _corpus = e2e_workspace
    runner = CliRunner()
    sync = runner.invoke(cli, ["sync", "-c", str(cfg_path)])
    assert sync.exit_code == 0, sync.output
    assert "Sync complete" in sync.output

    q = runner.invoke(cli, ["query", "-c", str(cfg_path), "private:",
                            "what is the rule about drivers with under 6 months?"])
    assert q.exit_code == 0, q.output
    # We don't assert on Ollama answer text (model-dependent), but citations must surface
    # the safety_policy.pdf file.
    assert "safety_policy.pdf" in q.output
