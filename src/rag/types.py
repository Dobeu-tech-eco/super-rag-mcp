"""Shared dataclasses passed between components."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ChangeEvent:
    """A document that has been created/modified/deleted in a source."""
    source: str            # "localfs" | "gdrive" | ...
    account: str           # alias, e.g. "personal-jeremy"
    doc_id: str            # source-stable identifier
    operation: str         # "upsert" | "delete"
    source_url: str        # link back to the original
    last_modified: datetime
    size_bytes: int | None = None
    mime: str | None = None


@dataclass
class RawDoc:
    """A document's raw bytes plus enough metadata to parse it."""
    doc_id: str
    source: str
    account: str
    source_url: str
    mime: str
    content: bytes
    filename: str
    last_modified: datetime


@dataclass
class ParsedDoc:
    """Parsed text + per-page mapping."""
    doc_id: str
    text: str
    page_texts: list[str]   # one entry per page; empty list for non-paged docs
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    """One indexable unit of text."""
    chunk_id: str          # "{source}:{account}:{doc_id}:{idx:05d}"
    doc_id: str
    chunk_idx: int
    text: str
    page_range: tuple[int, int] | None  # inclusive, 1-based; None for non-paged
    source_url: str


@dataclass
class Citation:
    chunk_id: str
    source_url: str
    excerpt: str
    page: int | None
    score: float


@dataclass
class Answer:
    text: str
    citations: list[Citation]
    private: bool
