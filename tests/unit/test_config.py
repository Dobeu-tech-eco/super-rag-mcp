from pathlib import Path
import pytest
from rag.config import Config, LocalfsSource, load_config


def test_load_minimal_config(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
sources:
  - kind: localfs
    paths:
      - /tmp/docs
embedding:
  model: bge-small-en-v1.5
  ollama_url: http://localhost:11434
  batch_size: 32
chunking:
  primary: sentence
  fallback_size: 512
  overlap: 64
ocr:
  enabled: true
  strategy: auto_detect
  min_chars_per_page: 100
llm:
  default: claude-cli
  private_prefix: "private:"
  private_tag_routes_to: ollama
  ollama_model: qwen2.5:7b
paths:
  bundle_dir: /tmp/bundles
  dlq: /tmp/dlq.jsonl
  metadata: /tmp/meta.sqlite
"""
    )
    cfg = load_config(cfg_file)
    assert isinstance(cfg, Config)
    assert len(cfg.sources) == 1
    assert isinstance(cfg.sources[0], LocalfsSource)
    assert cfg.sources[0].paths == [Path("/tmp/docs")]
    assert cfg.embedding.batch_size == 32
    assert cfg.llm.private_prefix == "private:"


def test_invalid_strategy_rejected(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
sources: []
embedding: {model: x, ollama_url: http://x, batch_size: 1}
chunking: {primary: sentence, fallback_size: 512, overlap: 64}
ocr: {enabled: true, strategy: bogus, min_chars_per_page: 100}
llm: {default: claude-cli, private_prefix: "p:", private_tag_routes_to: ollama, ollama_model: q}
paths: {bundle_dir: /tmp/b, dlq: /tmp/d.jsonl, metadata: /tmp/m.sqlite}
"""
    )
    with pytest.raises(ValueError):
        load_config(cfg_file)
