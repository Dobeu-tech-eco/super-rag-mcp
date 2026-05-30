"""Configuration loading and validation."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Union

import yaml
from pydantic import BaseModel, Field, field_validator


class LocalfsSource(BaseModel):
    kind: Literal["localfs"]
    paths: list[Path]


class GdriveSource(BaseModel):
    kind: Literal["gdrive"]
    accounts: list[str]
    include_paths: list[str] = Field(default_factory=lambda: ["/"])
    mime_filter: list[str] | None = None


class OneDriveSource(BaseModel):
    kind: Literal["onedrive"]
    accounts: list[str]
    mime_filter: list[str] | None = None


class GmailSource(BaseModel):
    kind: Literal["gmail"]
    accounts: list[str]
    attachment_only: bool = True
    mime_filter: list[str] | None = None


class OutlookSource(BaseModel):
    kind: Literal["outlook"]
    accounts: list[str]
    attachment_only: bool = True
    mime_filter: list[str] | None = None


SourceConfig = Union[LocalfsSource, GdriveSource, OneDriveSource, GmailSource, OutlookSource]


class EmbeddingConfig(BaseModel):
    model: str
    ollama_url: str
    batch_size: int = 32


class ChunkingConfig(BaseModel):
    primary: Literal["semantic", "sentence"] = "sentence"
    fallback_size: int = 512
    overlap: int = 64


class OcrConfig(BaseModel):
    enabled: bool = True
    strategy: Literal["auto_detect", "always", "never"] = "auto_detect"
    min_chars_per_page: int = 100


class LlmConfig(BaseModel):
    default: Literal["claude-cli", "ollama"] = "claude-cli"
    private_prefix: str = "private:"
    private_tag_routes_to: Literal["ollama", "claude-cli"] = "ollama"
    ollama_model: str = "qwen2.5:7b"


class PathsConfig(BaseModel):
    bundle_dir: Path
    dlq: Path
    metadata: Path


class ComposioConfig(BaseModel):
    api_key_env: str = "COMPOSIO_API_KEY"
    connected_accounts: dict[str, str] = Field(default_factory=dict)


class Config(BaseModel):
    sources: list[SourceConfig]
    embedding: EmbeddingConfig
    chunking: ChunkingConfig
    ocr: OcrConfig
    llm: LlmConfig
    paths: PathsConfig
    composio: ComposioConfig | None = None

    @field_validator("sources", mode="before")
    @classmethod
    def _dispatch_sources(cls, v):
        if not isinstance(v, list):
            return v
        out = []
        registry = {
            "localfs": LocalfsSource,
            "gdrive": GdriveSource,
            "onedrive": OneDriveSource,
            "gmail": GmailSource,
            "outlook": OutlookSource,
        }
        for item in v:
            if isinstance(item, BaseModel):
                out.append(item); continue
            kind = item.get("kind")
            if kind not in registry:
                raise ValueError(f"Unknown source kind: {kind}")
            out.append(registry[kind](**item))
        return out


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    return Config(**raw)
