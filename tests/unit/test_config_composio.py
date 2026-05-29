from pathlib import Path

from rag.config import ComposioConfig, load_config


def test_config_without_composio_block_still_loads(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
sources:
  - kind: localfs
    paths: [/tmp/docs]
embedding: {model: bge-small-en-v1.5, ollama_url: http://localhost:11434, batch_size: 32}
chunking: {primary: sentence, fallback_size: 512, overlap: 64}
ocr: {enabled: true, strategy: auto_detect, min_chars_per_page: 100}
llm: {default: claude-cli, private_prefix: "private:", private_tag_routes_to: ollama, ollama_model: q}
paths: {bundle_dir: /tmp/b, dlq: /tmp/d.jsonl, metadata: /tmp/m.sqlite}
"""
    )
    cfg = load_config(cfg_file)
    assert cfg.composio is None


def test_config_with_composio_block(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
sources:
  - kind: gdrive
    accounts: [personal-jeremy]
embedding: {model: bge-small-en-v1.5, ollama_url: http://localhost:11434, batch_size: 32}
chunking: {primary: sentence, fallback_size: 512, overlap: 64}
ocr: {enabled: true, strategy: auto_detect, min_chars_per_page: 100}
llm: {default: claude-cli, private_prefix: "private:", private_tag_routes_to: ollama, ollama_model: q}
paths: {bundle_dir: /tmp/b, dlq: /tmp/d.jsonl, metadata: /tmp/m.sqlite}
composio:
  api_key_env: COMPOSIO_API_KEY
  connected_accounts:
    personal-jeremy: ca_abc123
    work-baldor: ca_def456
"""
    )
    cfg = load_config(cfg_file)
    assert isinstance(cfg.composio, ComposioConfig)
    assert cfg.composio.api_key_env == "COMPOSIO_API_KEY"
    assert cfg.composio.connected_accounts["personal-jeremy"] == "ca_abc123"


def test_composio_config_defaults():
    c = ComposioConfig()
    assert c.api_key_env == "COMPOSIO_API_KEY"
    assert c.connected_accounts == {}
