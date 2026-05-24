# RAG MVP Implementation Plan (Plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working laptop-only RAG pipeline that ingests local files (PDF + DOCX + TXT, with OCR fallback for scanned PDFs), embeds them with a local Ollama model, indexes them in TurboVec, and answers questions via a CLI using Claude Code CLI for generation. This is the foundation — Plans 2, 3, 4 layer cloud connectors, MCP server, and VPS hybrid deployment on top.

**Architecture:** Single-host Python application. SQLite for metadata, TurboVec for vectors, Ollama for embeddings (BGE-small-en-v1.5), Claude Code CLI (Max auth) for generation with Ollama fallback for `private:`-tagged queries. No network components in Plan 1.

**Tech Stack:** Python 3.12, uv (package management), ruff (lint/format), pytest, sqlite-utils, pymupdf, pdfplumber, pytesseract, pdf2image, python-docx, llama-index-core, ollama (HTTP client), turbovec, click (CLI), pydantic (config schema).

**Prerequisites (one-time setup, not in plan tasks):**
- Python 3.12 installed on laptop
- `uv` installed (`pip install uv` or via installer)
- Ollama installed and running on `localhost:11434`
- Models pulled: `ollama pull bge-small-en-v1.5` and `ollama pull qwen2.5:7b`
- Tesseract installed (`choco install tesseract` on Windows)
- Poppler installed for pdf2image (`choco install poppler`)
- Claude Code CLI installed with Max auth completed (`claude login`)
- Repo clean: corrupted `.git` directory removed manually before Task 1

---

## File Structure

```
super-rag-gdrive-onedrive/
├── pyproject.toml                  # Task 1 — project metadata, deps
├── ruff.toml                        # Task 1 — lint config
├── .gitignore                       # Task 1
├── config.example.yaml              # Task 2 — example config
├── README.md                        # Task 1 — quickstart
├── src/rag/
│   ├── __init__.py                  # Task 1
│   ├── config.py                    # Task 2 — pydantic schemas + loader
│   ├── types.py                     # Task 3 — shared dataclasses (ChangeEvent, RawDoc, ParsedDoc, Chunk, Citation, Answer)
│   ├── metadata.py                  # Task 3 — SQLite store
│   ├── dlq.py                       # Task 4 — dead-letter queue
│   ├── parser.py                    # Task 5 — PDF/DOCX/TXT + OCR fallback
│   ├── chunker.py                   # Task 6 — sentence splitter
│   ├── embedder.py                  # Task 7 — Ollama HTTP wrapper
│   ├── index.py                     # Task 8 — TurboVec wrapper
│   ├── connectors/
│   │   ├── __init__.py              # Task 9 — Connector Protocol
│   │   └── localfs.py               # Task 10 — local filesystem connector
│   ├── sync.py                      # Task 11 — orchestrator
│   ├── llm.py                       # Task 12 — Claude CLI + Ollama backends
│   ├── query.py                     # Task 13 — embed→retrieve→hydrate→generate
│   └── serve/
│       ├── __init__.py              # Task 14
│       └── cli.py                   # Task 14 — click CLI
├── tests/
│   ├── __init__.py                  # Task 1
│   ├── conftest.py                  # Task 3
│   ├── fixtures/                    # Task 5 — test PDFs/DOCX
│   │   ├── text.pdf
│   │   ├── scanned.pdf
│   │   ├── sample.docx
│   │   └── sample.txt
│   ├── unit/
│   │   ├── test_config.py           # Task 2
│   │   ├── test_metadata.py         # Task 3
│   │   ├── test_dlq.py              # Task 4
│   │   ├── test_parser.py           # Task 5
│   │   ├── test_chunker.py          # Task 6
│   │   ├── test_embedder.py         # Task 7
│   │   ├── test_index.py            # Task 8
│   │   ├── test_localfs.py          # Task 10
│   │   ├── test_sync.py             # Task 11
│   │   ├── test_llm.py              # Task 12
│   │   └── test_query.py            # Task 13
│   └── integration/
│       └── test_e2e.py              # Task 15
└── .agent/
    ├── progress.md                  # Task 1
    ├── tasks.json                   # Task 1
    └── state.json                   # Task 1
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `ruff.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/rag/__init__.py`
- Create: `tests/__init__.py`
- Create: `.agent/progress.md`
- Create: `.agent/tasks.json`
- Create: `.agent/state.json`

- [ ] **Step 1: Confirm corrupted `.git` is gone**

User must have run `Remove-Item -Recurse -Force .git` in PowerShell at `C:\Users\jswil\repos\super-rag-gdrive-onedrive`. Verify with:

```bash
ls -la .git 2>&1 | head
```

Expected: `ls: cannot access '.git': No such file or directory`. If `.git` still exists, STOP — ask user to remove it.

- [ ] **Step 2: Initialize git and create `.gitignore`**

```bash
git init -b main
git config user.email "jswilliamstu@gmail.com"
git config user.name "Jeremy Williams"
```

Write `.gitignore`:

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.venv/
venv/
.pytest_cache/
.ruff_cache/

# RAG data
/var/lib/rag/
*.tq
*.sqlite
*.sqlite-journal
*.jsonl
bundles/
mirrors/

# Editor
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "super-rag"
version = "0.1.0"
description = "Self-hosted RAG over Drive/OneDrive/Email/Local using LlamaIndex + TurboVec"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
    "pyyaml>=6.0",
    "sqlite-utils>=3.36",
    "pymupdf>=1.24",
    "pdfplumber>=0.11",
    "pytesseract>=0.3.10",
    "pdf2image>=1.17",
    "python-docx>=1.1",
    "llama-index-core>=0.10",
    "httpx>=0.27",
    "click>=8.1",
    "turbovec>=0.1",
    "rich>=13.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "respx>=0.21",
]

[project.scripts]
rag = "rag.serve.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rag"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: requires real services (Ollama, Claude CLI)",
]

[tool.coverage.run]
branch = true
source = ["src/rag"]
```

- [ ] **Step 4: Create `ruff.toml`**

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "I", "B", "UP", "RUF"]
ignore = ["E501"]

[lint.per-file-ignores]
"tests/**" = ["B011"]
```

- [ ] **Step 5: Create empty package files and agent state**

```bash
mkdir -p src/rag/connectors src/rag/serve tests/unit tests/integration tests/fixtures .agent
echo '"""Super RAG package."""' > src/rag/__init__.py
echo '__version__ = "0.1.0"' >> src/rag/__init__.py
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

Write `.agent/progress.md`:

```markdown
# Progress Log

## 2026-05-23 — Plan 1 kickoff
- Spec approved: docs/superpowers/specs/2026-05-23-rag-pipeline-design.md
- Plan 1 (MVP) saved: docs/superpowers/plans/2026-05-23-rag-mvp-plan.md
- Starting Task 1: project scaffold
```

Write `.agent/tasks.json`:

```json
{
  "plan": "Plan 1 — RAG MVP",
  "started_at": "2026-05-23",
  "features": [
    {"id": 1, "title": "Project scaffold", "status": "in_progress", "passes": false, "priority": 1, "dependencies": []},
    {"id": 2, "title": "Config loader", "status": "pending", "passes": false, "priority": 2, "dependencies": [1]},
    {"id": 3, "title": "Metadata store", "status": "pending", "passes": false, "priority": 3, "dependencies": [1]},
    {"id": 4, "title": "DLQ", "status": "pending", "passes": false, "priority": 4, "dependencies": [1]},
    {"id": 5, "title": "Parser", "status": "pending", "passes": false, "priority": 5, "dependencies": [1]},
    {"id": 6, "title": "Chunker", "status": "pending", "passes": false, "priority": 6, "dependencies": [5]},
    {"id": 7, "title": "Embedder", "status": "pending", "passes": false, "priority": 7, "dependencies": [1]},
    {"id": 8, "title": "Index wrapper", "status": "pending", "passes": false, "priority": 8, "dependencies": [1]},
    {"id": 9, "title": "Connector protocol", "status": "pending", "passes": false, "priority": 9, "dependencies": [3]},
    {"id": 10, "title": "Localfs connector", "status": "pending", "passes": false, "priority": 10, "dependencies": [9]},
    {"id": 11, "title": "Sync orchestrator", "status": "pending", "passes": false, "priority": 11, "dependencies": [2,3,4,5,6,7,8,10]},
    {"id": 12, "title": "LLM backends", "status": "pending", "passes": false, "priority": 12, "dependencies": [1]},
    {"id": 13, "title": "Query module", "status": "pending", "passes": false, "priority": 13, "dependencies": [3,7,8,12]},
    {"id": 14, "title": "CLI", "status": "pending", "passes": false, "priority": 14, "dependencies": [11,13]},
    {"id": 15, "title": "End-to-end integration test", "status": "pending", "passes": false, "priority": 15, "dependencies": [14]}
  ]
}
```

Write `.agent/state.json`:

```json
{
  "working_directory": "C:\\Users\\jswil\\repos\\super-rag-gdrive-onedrive",
  "platform": "Cowork on Windows",
  "model": "claude-opus-4-7",
  "current_plan": "docs/superpowers/plans/2026-05-23-rag-mvp-plan.md",
  "current_task": 1,
  "git": {"branch": "main", "last_commit": null},
  "build_status": "not_yet_built",
  "test_status": "not_yet_run",
  "connections": ["composio (planned for Plan 2)", "claude_code_cli (planned for Task 12)", "ollama (planned for Task 7)"],
  "handoff_notes": "Plan 1 just started. Task 1 scaffolds the project."
}
```

- [ ] **Step 6: Install deps and verify**

```bash
uv venv && uv pip install -e ".[dev]"
```

Expected: `Successfully installed ...` and `.venv/` directory exists.

- [ ] **Step 7: Write `README.md`**

```markdown
# Super RAG — Drive + OneDrive + Email + Local

Self-hosted retrieval-augmented generation over your personal cloud and local documents.

## Status

Phase 1 of 4: Local-files MVP. See `docs/superpowers/plans/` for plan progression.

## Quickstart (after Phase 1 ships)

```bash
uv venv && uv pip install -e ".[dev]"
cp config.example.yaml config.yaml  # edit paths
rag sync
rag query "what does the safety policy say about new drivers?"
```

## Prerequisites

- Python 3.12
- Ollama with `bge-small-en-v1.5` and `qwen2.5:7b` pulled
- Tesseract + Poppler installed (for OCR)
- Claude Code CLI installed and authenticated

## Docs

- Design spec: `docs/superpowers/specs/2026-05-23-rag-pipeline-design.md`
- MVP plan: `docs/superpowers/plans/2026-05-23-rag-mvp-plan.md`
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "[SCAFFOLD] Task 1: project skeleton, deps, agent state

- pyproject.toml with all runtime + dev deps
- ruff config
- .gitignore for Python + RAG artifacts
- Empty package skeleton under src/rag
- .agent/{progress.md, tasks.json, state.json} for cross-session handoff
- README quickstart

Tests: none yet (no code)
Feature ID: 1"
```

---

## Task 2: Config Loader

**Files:**
- Create: `src/rag/config.py`
- Create: `config.example.yaml`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_config.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_config.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rag.config'`.

- [ ] **Step 3: Implement `src/rag/config.py`**

```python
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


class Config(BaseModel):
    sources: list[SourceConfig]
    embedding: EmbeddingConfig
    chunking: ChunkingConfig
    ocr: OcrConfig
    llm: LlmConfig
    paths: PathsConfig

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
```

- [ ] **Step 4: Create `config.example.yaml`**

```yaml
sources:
  - kind: localfs
    paths:
      - C:\Users\jswil\Documents\rag-test-corpus

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
  bundle_dir: C:\Users\jswil\rag-data\bundles
  dlq: C:\Users\jswil\rag-data\dlq.jsonl
  metadata: C:\Users\jswil\rag-data\meta.sqlite
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "[CONFIG] Task 2: pydantic config schema + YAML loader

- Discriminated source union (localfs, gdrive, onedrive, gmail, outlook)
- All sections from spec section 8 (embedding, chunking, ocr, llm, paths)
- config.example.yaml with Windows-friendly paths

Tests: 2 unit tests passing
Feature ID: 2"
```

---

## Task 3: Metadata Store

**Files:**
- Create: `src/rag/types.py`
- Create: `src/rag/metadata.py`
- Create: `tests/conftest.py`
- Test: `tests/unit/test_metadata.py`

- [ ] **Step 1: Write `src/rag/types.py` first (shared dataclasses)**

```python
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
```

- [ ] **Step 2: Write the failing test**

`tests/conftest.py`:

```python
import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

`tests/unit/test_metadata.py`:

```python
from datetime import datetime
from pathlib import Path
import pytest
from rag.metadata import MetadataStore
from rag.types import ChangeEvent, Chunk


@pytest.fixture
def store(tmp_path: Path) -> MetadataStore:
    return MetadataStore(tmp_path / "meta.sqlite")


def test_upsert_and_get_document(store: MetadataStore):
    event = ChangeEvent(
        source="localfs", account="default", doc_id="abc",
        operation="upsert", source_url="file:///tmp/x.pdf",
        last_modified=datetime(2026, 5, 23, 0, 0), size_bytes=1234, mime="application/pdf",
    )
    store.upsert_document(event, content_hash="deadbeef")
    doc = store.get_document("localfs", "default", "abc")
    assert doc is not None
    assert doc["content_hash"] == "deadbeef"
    assert doc["status"] == "indexed"


def test_mark_failed_and_deleted(store: MetadataStore):
    event = ChangeEvent(
        source="localfs", account="default", doc_id="abc",
        operation="upsert", source_url="file:///tmp/x.pdf",
        last_modified=datetime(2026, 5, 23), size_bytes=1, mime="text/plain",
    )
    store.upsert_document(event, content_hash="h")
    store.mark_failed("localfs", "default", "abc", reason="bad pdf")
    assert store.get_document("localfs", "default", "abc")["status"] == "failed"
    store.mark_deleted("localfs", "default", "abc")
    assert store.get_document("localfs", "default", "abc")["status"] == "deleted"


def test_chunks_roundtrip(store: MetadataStore):
    event = ChangeEvent(source="localfs", account="default", doc_id="abc",
                        operation="upsert", source_url="file:///x", last_modified=datetime(2026, 5, 23))
    store.upsert_document(event, content_hash="h")
    chunks = [
        Chunk(chunk_id="localfs:default:abc:00000", doc_id="abc", chunk_idx=0,
              text="hello", page_range=(1, 1), source_url="file:///x"),
        Chunk(chunk_id="localfs:default:abc:00001", doc_id="abc", chunk_idx=1,
              text="world", page_range=(1, 1), source_url="file:///x"),
    ]
    store.upsert_chunks(chunks)
    hydrated = store.hydrate_chunks(["localfs:default:abc:00001", "localfs:default:abc:00000"])
    assert {c["chunk_id"] for c in hydrated} == {c.chunk_id for c in chunks}


def test_run_log(store: MetadataStore):
    rid = store.start_run()
    store.finish_run(rid, status="success", docs_processed=10, chunks_indexed=42)
    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["chunks_indexed"] == 42
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/unit/test_metadata.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rag.metadata'`.

- [ ] **Step 4: Implement `src/rag/metadata.py`**

```python
"""SQLite-backed metadata store: documents, chunks, runs."""
from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from rag.types import ChangeEvent, Chunk


_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    source TEXT NOT NULL,
    account TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    mime TEXT,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER,
    last_modified TEXT,
    last_synced TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('indexed','failed','deleted')),
    failure_reason TEXT,
    PRIMARY KEY (source, account, doc_id)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    source TEXT NOT NULL,
    account TEXT NOT NULL,
    chunk_idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    source_url TEXT NOT NULL,
    FOREIGN KEY (source, account, doc_id) REFERENCES documents(source, account, doc_id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(source, account, doc_id);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    docs_processed INTEGER DEFAULT 0,
    chunks_indexed INTEGER DEFAULT 0,
    last_resumable_at TEXT
);
"""


class MetadataStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ----- documents -----

    def upsert_document(self, event: ChangeEvent, content_hash: str) -> None:
        now = datetime.utcnow().isoformat()
        self._conn.execute(
            """INSERT INTO documents (source, account, doc_id, source_url, mime,
                content_hash, size_bytes, last_modified, last_synced, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'indexed')
               ON CONFLICT(source, account, doc_id) DO UPDATE SET
                source_url=excluded.source_url, mime=excluded.mime,
                content_hash=excluded.content_hash, size_bytes=excluded.size_bytes,
                last_modified=excluded.last_modified, last_synced=excluded.last_synced,
                status='indexed', failure_reason=NULL""",
            (event.source, event.account, event.doc_id, event.source_url, event.mime,
             content_hash, event.size_bytes, event.last_modified.isoformat(), now),
        )
        self._conn.commit()

    def mark_failed(self, source: str, account: str, doc_id: str, reason: str) -> None:
        self._conn.execute(
            "UPDATE documents SET status='failed', failure_reason=? WHERE source=? AND account=? AND doc_id=?",
            (reason, source, account, doc_id),
        )
        # Insert minimal row if it didn't exist
        if self._conn.total_changes == 0:
            now = datetime.utcnow().isoformat()
            self._conn.execute(
                """INSERT OR IGNORE INTO documents
                    (source, account, doc_id, source_url, content_hash, last_synced, status, failure_reason)
                   VALUES (?, ?, ?, '', '', ?, 'failed', ?)""",
                (source, account, doc_id, now, reason),
            )
        self._conn.commit()

    def mark_deleted(self, source: str, account: str, doc_id: str) -> None:
        self._conn.execute(
            "UPDATE documents SET status='deleted' WHERE source=? AND account=? AND doc_id=?",
            (source, account, doc_id),
        )
        self._conn.execute(
            "DELETE FROM chunks WHERE source=? AND account=? AND doc_id=?",
            (source, account, doc_id),
        )
        self._conn.commit()

    def get_document(self, source: str, account: str, doc_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE source=? AND account=? AND doc_id=?",
            (source, account, doc_id),
        ).fetchone()
        return dict(row) if row else None

    # ----- chunks -----

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        rows = []
        for c in chunks:
            parsed_id = c.chunk_id.split(":")
            if len(parsed_id) < 4:
                raise ValueError(f"chunk_id must be source:account:doc:idx, got {c.chunk_id}")
            src, acct = parsed_id[0], parsed_id[1]
            page_start, page_end = (c.page_range or (None, None))
            rows.append((c.chunk_id, c.doc_id, src, acct, c.chunk_idx,
                         c.text, page_start, page_end, c.source_url))
        self._conn.executemany(
            """INSERT INTO chunks (chunk_id, doc_id, source, account, chunk_idx,
                                   text, page_start, page_end, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(chunk_id) DO UPDATE SET
                   text=excluded.text, page_start=excluded.page_start,
                   page_end=excluded.page_end""",
            rows,
        )
        self._conn.commit()

    def hydrate_chunks(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        qmarks = ",".join("?" * len(chunk_ids))
        rows = self._conn.execute(
            f"SELECT * FROM chunks WHERE chunk_id IN ({qmarks})",
            chunk_ids,
        ).fetchall()
        return [dict(r) for r in rows]

    # ----- runs -----

    def start_run(self) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (started_at) VALUES (?)",
            (datetime.utcnow().isoformat(),),
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, status: str, docs_processed: int,
                   chunks_indexed: int, last_resumable_at: str | None = None) -> None:
        self._conn.execute(
            """UPDATE runs SET finished_at=?, status=?, docs_processed=?,
                               chunks_indexed=?, last_resumable_at=?
               WHERE id=?""",
            (datetime.utcnow().isoformat(), status, docs_processed,
             chunks_indexed, last_resumable_at, run_id),
        )
        self._conn.commit()

    def list_runs(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def last_successful_run_at(self) -> datetime | None:
        row = self._conn.execute(
            "SELECT finished_at FROM runs WHERE status='success' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return datetime.fromisoformat(row["finished_at"]) if row else None
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_metadata.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "[META] Task 3: SQLite metadata store + shared types

- documents, chunks, runs tables with idempotent upserts
- Shared dataclasses (ChangeEvent, RawDoc, ParsedDoc, Chunk, Citation, Answer)
- hydrate_chunks for query-side rehydration

Tests: 4 unit tests passing
Feature ID: 3"
```

---

## Task 4: DLQ

**Files:**
- Create: `src/rag/dlq.py`
- Test: `tests/unit/test_dlq.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_dlq.py`:

```python
import json
from pathlib import Path
from rag.dlq import DeadLetterQueue


def test_write_and_iter(tmp_path: Path):
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    dlq.write(doc_id="abc", source="localfs", account="default",
              error="ValueError: bad pdf", traceback_str="Traceback...")
    dlq.write(doc_id="def", source="localfs", account="default",
              error="OSError: file gone", traceback_str="Traceback...")
    entries = list(dlq.iter_entries())
    assert len(entries) == 2
    assert entries[0]["doc_id"] == "abc"
    assert entries[0]["retry_count"] == 0


def test_replay_increments_retry(tmp_path: Path):
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    dlq.write(doc_id="abc", source="localfs", account="default",
              error="x", traceback_str="t")
    dlq.mark_retried("abc", "localfs", "default")
    entries = list(dlq.iter_entries())
    assert entries[0]["retry_count"] == 1


def test_filter_by_source(tmp_path: Path):
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")
    dlq.write(doc_id="a", source="localfs", account="x", error="e", traceback_str="t")
    dlq.write(doc_id="b", source="gdrive", account="y", error="e", traceback_str="t")
    locals_ = list(dlq.iter_entries(source="localfs"))
    assert len(locals_) == 1 and locals_[0]["doc_id"] == "a"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_dlq.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rag.dlq'`.

- [ ] **Step 3: Implement `src/rag/dlq.py`**

```python
"""Dead-letter queue stored as JSONL."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Iterator


class DeadLetterQueue:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def write(self, doc_id: str, source: str, account: str,
              error: str, traceback_str: str) -> None:
        # Check if entry already exists; if so, do nothing here (mark_retried updates).
        for entry in self.iter_entries():
            if entry["doc_id"] == doc_id and entry["source"] == source and entry["account"] == account:
                return
        record = {
            "doc_id": doc_id,
            "source": source,
            "account": account,
            "error": error,
            "traceback": traceback_str,
            "retry_count": 0,
            "first_failed_at": datetime.utcnow().isoformat(),
            "last_failed_at": datetime.utcnow().isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def iter_entries(self, source: str | None = None) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if source and rec["source"] != source:
                    continue
                yield rec

    def mark_retried(self, doc_id: str, source: str, account: str) -> None:
        entries = list(self.iter_entries())
        for e in entries:
            if e["doc_id"] == doc_id and e["source"] == source and e["account"] == account:
                e["retry_count"] = e.get("retry_count", 0) + 1
                e["last_failed_at"] = datetime.utcnow().isoformat()
        with self.path.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_dlq.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[DLQ] Task 4: append-only JSONL dead-letter queue

- write/iter_entries/mark_retried
- Optional source filter for replay
- Idempotent writes (no duplicates per doc_id+source+account)

Tests: 3 unit tests passing
Feature ID: 4"
```

---

## Task 5: Parser (PDF + OCR fallback + DOCX + TXT)

**Files:**
- Create: `src/rag/parser.py`
- Create: `tests/fixtures/sample.txt`
- Test: `tests/unit/test_parser.py`

**Note for engineer:** The fixtures `text.pdf`, `scanned.pdf`, and `sample.docx` should be added by the user — the engineer cannot generate scanned PDFs from scratch. Use this command before running tests:

```bash
python -c "
from pathlib import Path
import fitz
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 72), 'Hello text PDF for testing.')
doc.save('tests/fixtures/text.pdf')
doc.close()
print('text.pdf generated')

from docx import Document
d = Document()
d.add_paragraph('Hello DOCX for testing.')
d.save('tests/fixtures/sample.docx')
print('sample.docx generated')
"
echo 'plain text fixture' > tests/fixtures/sample.txt
```

The scanned.pdf fixture should be a real scanned PDF the user supplies; until then, OCR test is marked skip.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_parser.py`:

```python
from datetime import datetime
from pathlib import Path
import pytest
from rag.parser import parse
from rag.types import RawDoc


def _raw(filename: str, content: bytes, mime: str) -> RawDoc:
    return RawDoc(
        doc_id=filename, source="localfs", account="default",
        source_url=f"file:///{filename}", mime=mime,
        content=content, filename=filename, last_modified=datetime(2026, 5, 23),
    )


def test_parse_text_pdf(fixtures_dir: Path):
    data = (fixtures_dir / "text.pdf").read_bytes()
    parsed = parse(_raw("text.pdf", data, "application/pdf"), ocr_strategy="auto_detect")
    assert "Hello text PDF" in parsed.text
    assert len(parsed.page_texts) >= 1
    assert parsed.metadata["used_ocr"] is False


def test_parse_docx(fixtures_dir: Path):
    data = (fixtures_dir / "sample.docx").read_bytes()
    parsed = parse(_raw("sample.docx", data,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                   ocr_strategy="auto_detect")
    assert "Hello DOCX" in parsed.text


def test_parse_txt(fixtures_dir: Path):
    data = (fixtures_dir / "sample.txt").read_bytes()
    parsed = parse(_raw("sample.txt", data, "text/plain"), ocr_strategy="auto_detect")
    assert "plain text fixture" in parsed.text


def test_parse_unsupported_mime_raises():
    with pytest.raises(ValueError, match="unsupported"):
        parse(_raw("x.bin", b"\x00\x01", "application/octet-stream"),
              ocr_strategy="auto_detect")


@pytest.mark.skipif(
    not (Path(__file__).parent.parent / "fixtures" / "scanned.pdf").exists(),
    reason="scanned.pdf fixture not provided",
)
def test_parse_scanned_pdf_uses_ocr(fixtures_dir: Path):
    data = (fixtures_dir / "scanned.pdf").read_bytes()
    parsed = parse(_raw("scanned.pdf", data, "application/pdf"), ocr_strategy="auto_detect")
    assert parsed.metadata["used_ocr"] is True
    assert len(parsed.text) > 0
```

- [ ] **Step 2: Generate fixtures and run test to verify it fails**

```bash
python -c "
import fitz
doc = fitz.open(); page = doc.new_page()
page.insert_text((72, 72), 'Hello text PDF for testing.')
doc.save('tests/fixtures/text.pdf'); doc.close()
from docx import Document
d = Document(); d.add_paragraph('Hello DOCX for testing.')
d.save('tests/fixtures/sample.docx')
"
echo plain text fixture > tests/fixtures/sample.txt
pytest tests/unit/test_parser.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rag.parser'`.

- [ ] **Step 3: Implement `src/rag/parser.py`**

```python
"""Document parser with PDF text extraction + OCR fallback + DOCX + TXT."""
from __future__ import annotations
from io import BytesIO
from typing import Literal
import fitz  # pymupdf
from docx import Document as DocxDocument
from rag.types import ParsedDoc, RawDoc

OcrStrategy = Literal["auto_detect", "always", "never"]

_TEXT_MIMES = {"text/plain", "text/markdown"}
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def parse(raw: RawDoc, ocr_strategy: OcrStrategy = "auto_detect",
          min_chars_per_page: int = 100) -> ParsedDoc:
    if raw.mime == "application/pdf":
        return _parse_pdf(raw, ocr_strategy, min_chars_per_page)
    if raw.mime == _DOCX_MIME:
        return _parse_docx(raw)
    if raw.mime in _TEXT_MIMES:
        return _parse_text(raw)
    raise ValueError(f"unsupported MIME for parser: {raw.mime}")


def _parse_pdf(raw: RawDoc, ocr_strategy: OcrStrategy, min_chars_per_page: int) -> ParsedDoc:
    doc = fitz.open(stream=raw.content, filetype="pdf")
    try:
        page_texts: list[str] = []
        for page in doc:
            page_texts.append(page.get_text() or "")
        total_chars = sum(len(t) for t in page_texts)
        avg = total_chars / max(1, len(page_texts))
        used_ocr = False
        if ocr_strategy == "always" or (ocr_strategy == "auto_detect" and avg < min_chars_per_page):
            page_texts = _ocr_pdf(raw.content)
            used_ocr = True
        return ParsedDoc(
            doc_id=raw.doc_id,
            text="\n\n".join(page_texts),
            page_texts=page_texts,
            metadata={"used_ocr": used_ocr, "page_count": len(page_texts)},
        )
    finally:
        doc.close()


def _ocr_pdf(content: bytes) -> list[str]:
    # Lazy import — OCR deps are heavy and not always available.
    from pdf2image import convert_from_bytes
    import pytesseract
    images = convert_from_bytes(content, dpi=200)
    texts: list[str] = []
    for img in images:
        texts.append(pytesseract.image_to_string(img) or "")
    return texts


def _parse_docx(raw: RawDoc) -> ParsedDoc:
    doc = DocxDocument(BytesIO(raw.content))
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    text = "\n".join(paragraphs)
    return ParsedDoc(
        doc_id=raw.doc_id,
        text=text,
        page_texts=[text],  # DOCX has no native pages
        metadata={"used_ocr": False, "paragraph_count": len(paragraphs)},
    )


def _parse_text(raw: RawDoc) -> ParsedDoc:
    text = raw.content.decode("utf-8", errors="replace")
    return ParsedDoc(
        doc_id=raw.doc_id,
        text=text,
        page_texts=[text],
        metadata={"used_ocr": False},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_parser.py -v
```

Expected: 4 passed (+ 1 skipped if scanned.pdf not provided).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[PARSE] Task 5: PDF + DOCX + TXT parser with OCR fallback

- PyMuPDF for text PDFs, pdfplumber fallback path reserved
- Tesseract + pdf2image lazy-imported for OCR
- auto_detect heuristic: <100 chars/page triggers OCR
- DOCX via python-docx, TXT plain decode
- ParsedDoc carries per-page texts and used_ocr metadata

Tests: 4 unit tests passing, 1 skip (needs scanned fixture)
Feature ID: 5"
```

---

## Task 6: Chunker

**Files:**
- Create: `src/rag/chunker.py`
- Test: `tests/unit/test_chunker.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_chunker.py`:

```python
from rag.chunker import chunk_document
from rag.types import ParsedDoc


def test_chunks_short_doc_into_one_chunk():
    parsed = ParsedDoc(doc_id="abc", text="A short document.",
                       page_texts=["A short document."], metadata={})
    chunks = chunk_document(parsed, source="localfs", account="default",
                            source_url="file:///x", chunk_size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0].text == "A short document."
    assert chunks[0].chunk_idx == 0
    assert chunks[0].chunk_id == "localfs:default:abc:00000"
    assert chunks[0].page_range == (1, 1)


def test_chunks_long_doc_into_many():
    text = "Sentence A. " * 200  # ~2400 chars, should split into multiple chunks
    parsed = ParsedDoc(doc_id="abc", text=text, page_texts=[text], metadata={})
    chunks = chunk_document(parsed, source="localfs", account="default",
                            source_url="file:///x", chunk_size=200, overlap=20)
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c.chunk_idx == i
        assert c.chunk_id == f"localfs:default:abc:{i:05d}"


def test_chunks_preserves_page_range_for_pdf():
    pages = ["Page one content.", "Page two content.", "Page three content."]
    parsed = ParsedDoc(doc_id="abc", text="\n\n".join(pages), page_texts=pages, metadata={})
    chunks = chunk_document(parsed, source="localfs", account="default",
                            source_url="file:///x", chunk_size=512, overlap=0)
    assert all(c.page_range is not None for c in chunks)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_chunker.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/rag/chunker.py`**

```python
"""Sentence-aware chunker that preserves source-page mapping."""
from __future__ import annotations
from llama_index.core.node_parser import SentenceSplitter
from rag.types import Chunk, ParsedDoc


def chunk_document(parsed: ParsedDoc, source: str, account: str, source_url: str,
                   chunk_size: int = 512, overlap: int = 64) -> list[Chunk]:
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
    text_chunks = splitter.split_text(parsed.text)

    # Build a character-to-page index for page-range derivation.
    page_breaks: list[tuple[int, int]] = []  # (char_end_exclusive, page_num)
    cursor = 0
    for i, page in enumerate(parsed.page_texts, start=1):
        cursor += len(page) + 2  # "\n\n" join in parse_pdf
        page_breaks.append((cursor, i))

    def page_range_for(chunk_text: str, search_from: int) -> tuple[int, int] | None:
        if not page_breaks:
            return None
        start = parsed.text.find(chunk_text, search_from)
        if start < 0:
            start = search_from
        end = start + len(chunk_text)
        first = next((p for ce, p in page_breaks if ce > start), page_breaks[-1][1])
        last = next((p for ce, p in page_breaks if ce >= end), page_breaks[-1][1])
        return (first, last)

    chunks: list[Chunk] = []
    cursor = 0
    for idx, text in enumerate(text_chunks):
        pr = page_range_for(text, cursor)
        if pr is None:
            pr = (1, 1)
        chunks.append(Chunk(
            chunk_id=f"{source}:{account}:{parsed.doc_id}:{idx:05d}",
            doc_id=parsed.doc_id,
            chunk_idx=idx,
            text=text,
            page_range=pr,
            source_url=source_url,
        ))
        cursor += max(1, len(text) - overlap)
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_chunker.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[CHUNK] Task 6: sentence-aware chunker with page-range derivation

- LlamaIndex SentenceSplitter primary
- Chunk IDs follow {source}:{account}:{doc_id}:{idx:05d} convention
- page_range derived from per-page text offsets in ParsedDoc

Tests: 3 unit tests passing
Feature ID: 6"
```

---

## Task 7: Embedder (Ollama wrapper)

**Files:**
- Create: `src/rag/embedder.py`
- Test: `tests/unit/test_embedder.py`

- [ ] **Step 1: Write the failing test (mocked HTTP)**

`tests/unit/test_embedder.py`:

```python
import httpx
import pytest
import respx
from rag.embedder import OllamaEmbedder


@respx.mock
def test_embed_query():
    respx.post("http://localhost:11434/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})
    )
    e = OllamaEmbedder(model="bge-small-en-v1.5", base_url="http://localhost:11434")
    v = e.embed_query("hello")
    assert v == [0.1, 0.2, 0.3]


@respx.mock
def test_embed_batch_returns_one_vector_per_text():
    respx.post("http://localhost:11434/api/embeddings").mock(
        side_effect=lambda req: httpx.Response(200, json={"embedding": [0.5, 0.5, 0.5]})
    )
    e = OllamaEmbedder(model="bge-small-en-v1.5", base_url="http://localhost:11434", batch_size=2)
    vectors = e.embed_batch(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 3 for v in vectors)


@respx.mock
def test_embed_propagates_http_errors():
    respx.post("http://localhost:11434/api/embeddings").mock(
        return_value=httpx.Response(500, text="boom")
    )
    e = OllamaEmbedder(model="bge-small-en-v1.5", base_url="http://localhost:11434")
    with pytest.raises(httpx.HTTPStatusError):
        e.embed_query("hello")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_embedder.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/rag/embedder.py`**

```python
"""Ollama-backed embedder. One interface, used identically on ingest and query sides."""
from __future__ import annotations
import httpx


class OllamaEmbedder:
    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 batch_size: int = 32, timeout: float = 60.0) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def embed_query(self, text: str) -> list[float]:
        resp = self._client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama embeddings endpoint is one-text-per-call.
        # Batch here means how many we issue before yielding control.
        out: list[list[float]] = []
        for chunk_start in range(0, len(texts), self.batch_size):
            for t in texts[chunk_start:chunk_start + self.batch_size]:
                out.append(self.embed_query(t))
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_embedder.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[EMBED] Task 7: Ollama HTTP embedder

- POST /api/embeddings for both query and batch (Ollama is one-at-a-time)
- batch_size controls cooperative yielding granularity
- Used identically on ingest and query sides for vector-space consistency

Tests: 3 unit tests passing (respx-mocked HTTP)
Feature ID: 7"
```

---

## Task 8: Index Wrapper (TurboVec)

**Files:**
- Create: `src/rag/index.py`
- Test: `tests/unit/test_index.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_index.py`:

```python
from pathlib import Path
import numpy as np
import pytest
from rag.index import VectorIndex


def test_add_and_search_roundtrip(tmp_path: Path):
    idx = VectorIndex(dim=4, path=tmp_path / "index.tq")
    ids = ["localfs:default:a:00000", "localfs:default:a:00001", "localfs:default:b:00000"]
    vecs = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [1, 1, 0, 0]], dtype=np.float32)
    idx.add_batch(ids, vecs)
    results = idx.search(np.array([1, 0, 0, 0], dtype=np.float32), k=2)
    assert len(results) == 2
    assert results[0][0] == "localfs:default:a:00000"  # closest to query


def test_delete_by_doc_id(tmp_path: Path):
    idx = VectorIndex(dim=4, path=tmp_path / "index.tq")
    ids = ["localfs:default:a:00000", "localfs:default:a:00001", "localfs:default:b:00000"]
    vecs = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], dtype=np.float32)
    idx.add_batch(ids, vecs)
    idx.delete_by_doc_id("localfs", "default", "a")
    results = idx.search(np.array([1, 0, 0, 0], dtype=np.float32), k=5)
    returned_ids = [r[0] for r in results]
    assert "localfs:default:a:00000" not in returned_ids
    assert "localfs:default:a:00001" not in returned_ids
    assert "localfs:default:b:00000" in returned_ids


def test_persist_and_reload(tmp_path: Path):
    p = tmp_path / "index.tq"
    idx = VectorIndex(dim=4, path=p)
    idx.add_batch(["localfs:default:a:00000"], np.array([[1, 0, 0, 0]], dtype=np.float32))
    idx.save()
    idx2 = VectorIndex.load(dim=4, path=p)
    results = idx2.search(np.array([1, 0, 0, 0], dtype=np.float32), k=1)
    assert results[0][0] == "localfs:default:a:00000"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_index.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/rag/index.py`**

```python
"""TurboVec IdMapIndex wrapper with stable string IDs and per-doc deletes."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import turbovec


class VectorIndex:
    def __init__(self, dim: int, path: Path) -> None:
        self.dim = dim
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._idx = turbovec.IdMapIndex(dim=dim)

    @classmethod
    def load(cls, dim: int, path: Path) -> "VectorIndex":
        inst = cls(dim, path)
        if inst.path.exists():
            inst._idx = turbovec.IdMapIndex.load(str(inst.path))
        return inst

    def add_batch(self, ids: list[str], vectors: np.ndarray) -> None:
        if vectors.shape[1] != self.dim:
            raise ValueError(f"Expected dim={self.dim}, got {vectors.shape[1]}")
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)
        self._idx.add(ids=ids, vectors=vectors)

    def delete_by_doc_id(self, source: str, account: str, doc_id: str) -> None:
        prefix = f"{source}:{account}:{doc_id}:"
        all_ids = self._idx.get_all_ids()
        to_delete = [i for i in all_ids if i.startswith(prefix)]
        if to_delete:
            self._idx.remove(ids=to_delete)

    def search(self, query: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        if query.dtype != np.float32:
            query = query.astype(np.float32)
        ids, scores = self._idx.search(query=query, k=k)
        return list(zip(ids, scores))

    def save(self) -> None:
        self._idx.save(str(self.path))
```

**Engineer note on TurboVec API:** the methods `add`, `remove`, `search`, `get_all_ids`, `save`, `load` reflect the library's surface as documented. If real method names differ, adapt the wrapper to the actual surface — the public methods of `VectorIndex` must stay the same so the rest of the system is insulated. Use `python -c "import turbovec; help(turbovec.IdMapIndex)"` to verify.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_index.py -v
```

Expected: 3 passed. If TurboVec method names differ, adjust the wrapper internals and re-run until green.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[INDEX] Task 8: TurboVec IdMapIndex wrapper

- Stable string IDs (source:account:doc_id:idx)
- delete_by_doc_id uses prefix scan over get_all_ids
- save/load for persistent bundles

Tests: 3 unit tests passing
Feature ID: 8"
```

---

## Task 9: Connector Protocol

**Files:**
- Create: `src/rag/connectors/__init__.py`

- [ ] **Step 1: Implement the Protocol**

`src/rag/connectors/__init__.py`:

```python
"""Connector base — every source implements this."""
from __future__ import annotations
from datetime import datetime
from typing import Iterator, Protocol
from rag.types import ChangeEvent, RawDoc


class Connector(Protocol):
    """A source-of-documents implementation.

    Implementations MUST:
    - Make list_changes idempotent — calling it with the same `since` is safe.
    - Make fetch_content idempotent — same doc_id always returns equivalent content (modulo source changes).
    - Never raise on individual missing docs; instead, yield ChangeEvent(operation='delete').
    - Surface auth failures by raising ConnectorAuthError so the orchestrator can notify.
    """

    name: str  # e.g. "localfs", "gdrive"

    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]:
        ...

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        ...


class ConnectorError(Exception):
    """Base class for connector errors."""


class ConnectorAuthError(ConnectorError):
    """Source authentication expired or invalid."""


class ConnectorRateLimitError(ConnectorError):
    """Source rate-limited the request."""
```

- [ ] **Step 2: Commit (no tests yet — Protocol is type-only)**

```bash
git add -A
git commit -m "[CONN] Task 9: Connector Protocol + error taxonomy

- Connector is a typing.Protocol with list_changes + fetch_content
- ConnectorAuthError / ConnectorRateLimitError for orchestrator routing

Tests: none (Protocol type only — exercised in Task 10)
Feature ID: 9"
```

---

## Task 10: Localfs Connector

**Files:**
- Create: `src/rag/connectors/localfs.py`
- Test: `tests/unit/test_localfs.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_localfs.py`:

```python
from datetime import datetime, timedelta
from pathlib import Path
from rag.connectors.localfs import LocalfsConnector


def _touch(p: Path, content: str = "x") -> None:
    p.write_text(content, encoding="utf-8")


def test_list_changes_picks_up_new_files(tmp_path: Path):
    _touch(tmp_path / "a.txt", "hello")
    _touch(tmp_path / "b.pdf")  # not a real PDF but extension drives MIME guess
    conn = LocalfsConnector(roots=[tmp_path])
    changes = list(conn.list_changes(account="default", since=None))
    assert len(changes) == 2
    assert all(c.operation == "upsert" for c in changes)
    assert {Path(c.doc_id).name for c in changes} == {"a.txt", "b.pdf"}


def test_list_changes_respects_since(tmp_path: Path):
    f = tmp_path / "a.txt"
    _touch(f, "hello")
    conn = LocalfsConnector(roots=[tmp_path])
    future = datetime.utcnow() + timedelta(days=1)
    changes = list(conn.list_changes(account="default", since=future))
    assert len(changes) == 0


def test_fetch_content_returns_bytes(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello world", encoding="utf-8")
    conn = LocalfsConnector(roots=[tmp_path])
    raw = conn.fetch_content(account="default", doc_id=str(f))
    assert raw.content == b"hello world"
    assert raw.source == "localfs"
    assert raw.mime == "text/plain"


def test_deleted_files_emit_delete_event(tmp_path: Path):
    f = tmp_path / "a.txt"
    _touch(f)
    conn = LocalfsConnector(roots=[tmp_path])
    seen = list(conn.list_changes(account="default", since=None))
    assert seen[0].operation == "upsert"

    f.unlink()
    # The connector remembers previously-seen files via a manifest beside the root
    # so deletes are observable on the next list_changes call.
    second = list(conn.list_changes(account="default", since=None))
    assert any(c.operation == "delete" for c in second)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_localfs.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/rag/connectors/localfs.py`**

```python
"""Local filesystem connector. Walks configured roots, emits ChangeEvents.

Maintains a tiny per-root manifest file (`.rag-localfs-manifest.json`) inside
each root so deletes become observable across runs.
"""
from __future__ import annotations
import hashlib
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Iterator
from rag.types import ChangeEvent, RawDoc

_MANIFEST_NAME = ".rag-localfs-manifest.json"
_SUPPORTED_EXTS = {".pdf", ".txt", ".md", ".docx"}


class LocalfsConnector:
    name = "localfs"

    def __init__(self, roots: list[Path]) -> None:
        self.roots = [Path(r) for r in roots]

    def list_changes(self, account: str, since: datetime | None) -> Iterator[ChangeEvent]:
        for root in self.roots:
            yield from self._scan_root(root, account, since)

    def _scan_root(self, root: Path, account: str,
                   since: datetime | None) -> Iterator[ChangeEvent]:
        if not root.exists():
            return
        manifest_path = root / _MANIFEST_NAME
        previous: dict[str, dict] = {}
        if manifest_path.exists():
            previous = json.loads(manifest_path.read_text())
        current: dict[str, dict] = {}

        for path in root.rglob("*"):
            if path.is_dir():
                continue
            if path.name == _MANIFEST_NAME:
                continue
            if path.suffix.lower() not in _SUPPORTED_EXTS:
                continue

            stat = path.stat()
            mtime = datetime.utcfromtimestamp(stat.st_mtime)
            doc_id = str(path)
            current[doc_id] = {"mtime": mtime.isoformat(), "size": stat.st_size}

            if since and mtime <= since:
                continue

            mime, _ = mimetypes.guess_type(path.name)
            if mime is None:
                mime = "application/octet-stream"

            yield ChangeEvent(
                source=self.name,
                account=account,
                doc_id=doc_id,
                operation="upsert",
                source_url=path.as_uri(),
                last_modified=mtime,
                size_bytes=stat.st_size,
                mime=mime,
            )

        # Emit deletes for anything seen before but not now.
        for prev_id in previous:
            if prev_id not in current:
                yield ChangeEvent(
                    source=self.name,
                    account=account,
                    doc_id=prev_id,
                    operation="delete",
                    source_url=Path(prev_id).as_uri() if prev_id else "",
                    last_modified=datetime.utcnow(),
                )

        manifest_path.write_text(json.dumps(current, indent=2))

    def fetch_content(self, account: str, doc_id: str) -> RawDoc:
        path = Path(doc_id)
        content = path.read_bytes()
        mime, _ = mimetypes.guess_type(path.name)
        if mime is None:
            mime = "application/octet-stream"
        stat = path.stat()
        return RawDoc(
            doc_id=doc_id,
            source=self.name,
            account=account,
            source_url=path.as_uri(),
            mime=mime,
            content=content,
            filename=path.name,
            last_modified=datetime.utcfromtimestamp(stat.st_mtime),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_localfs.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[LOCALFS] Task 10: filesystem connector with delete detection

- Walks configured roots, filters by supported extension
- Per-root manifest file enables cross-run delete detection
- Respects 'since' for incremental scans
- doc_id is absolute path string (stable, addressable)

Tests: 4 unit tests passing
Feature ID: 10"
```

---

## Task 11: Sync Orchestrator

**Files:**
- Create: `src/rag/sync.py`
- Test: `tests/unit/test_sync.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_sync.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest
from rag.sync import SyncOrchestrator
from rag.types import ChangeEvent, RawDoc


@pytest.fixture
def fake_embedder():
    emb = MagicMock()
    emb.embed_batch.side_effect = lambda texts: [[0.1, 0.2, 0.3, 0.4]] * len(texts)
    return emb


@pytest.fixture
def fake_index():
    idx = MagicMock()
    return idx


@pytest.fixture
def fake_connector(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello orchestrator", encoding="utf-8")

    conn = MagicMock()
    conn.name = "localfs"
    conn.list_changes.return_value = iter([
        ChangeEvent(source="localfs", account="default", doc_id=str(f),
                    operation="upsert", source_url=f.as_uri(),
                    last_modified=datetime(2026, 5, 23), size_bytes=f.stat().st_size,
                    mime="text/plain"),
    ])
    conn.fetch_content.return_value = RawDoc(
        doc_id=str(f), source="localfs", account="default",
        source_url=f.as_uri(), mime="text/plain",
        content=b"hello orchestrator", filename=f.name,
        last_modified=datetime(2026, 5, 23),
    )
    return conn


def test_orchestrator_indexes_one_doc(tmp_path: Path, fake_connector, fake_embedder, fake_index):
    from rag.metadata import MetadataStore
    from rag.dlq import DeadLetterQueue
    meta = MetadataStore(tmp_path / "meta.sqlite")
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")

    orch = SyncOrchestrator(
        connectors={"localfs": fake_connector},
        accounts_per_connector={"localfs": ["default"]},
        embedder=fake_embedder, index=fake_index,
        metadata=meta, dlq=dlq,
        chunk_size=512, overlap=64, ocr_strategy="never",
    )
    result = orch.run()
    assert result.docs_processed == 1
    assert result.chunks_indexed >= 1
    assert result.docs_failed == 0
    fake_index.add_batch.assert_called_once()


def test_orchestrator_isolates_per_doc_failure(tmp_path: Path, fake_embedder, fake_index):
    from rag.metadata import MetadataStore
    from rag.dlq import DeadLetterQueue
    meta = MetadataStore(tmp_path / "meta.sqlite")
    dlq = DeadLetterQueue(tmp_path / "dlq.jsonl")

    good = tmp_path / "good.txt"; good.write_text("ok", encoding="utf-8")
    bad = tmp_path / "bad.txt"; bad.write_text("boom", encoding="utf-8")

    conn = MagicMock()
    conn.name = "localfs"
    conn.list_changes.return_value = iter([
        ChangeEvent(source="localfs", account="default", doc_id=str(good),
                    operation="upsert", source_url=good.as_uri(),
                    last_modified=datetime(2026, 5, 23), mime="text/plain"),
        ChangeEvent(source="localfs", account="default", doc_id=str(bad),
                    operation="upsert", source_url=bad.as_uri(),
                    last_modified=datetime(2026, 5, 23), mime="text/plain"),
    ])

    def fetch(account, doc_id):
        if "bad" in doc_id:
            raise OSError("simulated read failure")
        return RawDoc(doc_id=doc_id, source="localfs", account=account,
                      source_url=Path(doc_id).as_uri(), mime="text/plain",
                      content=b"ok", filename=Path(doc_id).name,
                      last_modified=datetime(2026, 5, 23))
    conn.fetch_content.side_effect = fetch

    orch = SyncOrchestrator(
        connectors={"localfs": conn}, accounts_per_connector={"localfs": ["default"]},
        embedder=fake_embedder, index=fake_index,
        metadata=meta, dlq=dlq,
        chunk_size=512, overlap=64, ocr_strategy="never",
    )
    result = orch.run()
    assert result.docs_processed == 1
    assert result.docs_failed == 1
    assert len(list(dlq.iter_entries())) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_sync.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/rag/sync.py`**

```python
"""Sync orchestrator: walks connectors, parses, chunks, embeds, indexes."""
from __future__ import annotations
import hashlib
import logging
import traceback
from dataclasses import dataclass
from typing import Iterable
import numpy as np
from rag.chunker import chunk_document
from rag.connectors import Connector, ConnectorAuthError
from rag.dlq import DeadLetterQueue
from rag.embedder import OllamaEmbedder
from rag.index import VectorIndex
from rag.metadata import MetadataStore
from rag.parser import parse
from rag.types import ChangeEvent

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    docs_processed: int
    docs_failed: int
    chunks_indexed: int


class SyncOrchestrator:
    def __init__(
        self,
        connectors: dict[str, Connector],
        accounts_per_connector: dict[str, list[str]],
        embedder: OllamaEmbedder,
        index: VectorIndex,
        metadata: MetadataStore,
        dlq: DeadLetterQueue,
        chunk_size: int = 512,
        overlap: int = 64,
        ocr_strategy: str = "auto_detect",
    ) -> None:
        self.connectors = connectors
        self.accounts_per_connector = accounts_per_connector
        self.embedder = embedder
        self.index = index
        self.metadata = metadata
        self.dlq = dlq
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.ocr_strategy = ocr_strategy

    def run(self) -> RunResult:
        run_id = self.metadata.start_run()
        docs_processed = 0
        docs_failed = 0
        chunks_indexed = 0
        try:
            since = self.metadata.last_successful_run_at()
            for source_name, conn in self.connectors.items():
                accounts = self.accounts_per_connector.get(source_name, [])
                for account in accounts:
                    try:
                        events: Iterable[ChangeEvent] = conn.list_changes(account, since)
                    except ConnectorAuthError as e:
                        log.error("auth error for %s/%s: %s", source_name, account, e)
                        continue
                    except Exception as e:
                        log.exception("listing failed for %s/%s", source_name, account)
                        continue

                    for event in events:
                        if event.operation == "delete":
                            self.metadata.mark_deleted(event.source, event.account, event.doc_id)
                            self.index.delete_by_doc_id(event.source, event.account, event.doc_id)
                            continue
                        try:
                            chunks_added = self._process_doc(conn, event)
                            docs_processed += 1
                            chunks_indexed += chunks_added
                        except Exception as e:
                            docs_failed += 1
                            tb = traceback.format_exc()
                            log.warning("doc failed: %s/%s/%s: %s",
                                        event.source, event.account, event.doc_id, e)
                            self.dlq.write(doc_id=event.doc_id, source=event.source,
                                           account=event.account, error=str(e), traceback_str=tb)
                            self.metadata.mark_failed(event.source, event.account,
                                                     event.doc_id, reason=str(e))
            self.metadata.finish_run(run_id, status="success",
                                     docs_processed=docs_processed, chunks_indexed=chunks_indexed)
            return RunResult(docs_processed, docs_failed, chunks_indexed)
        except Exception:
            self.metadata.finish_run(run_id, status="crashed",
                                     docs_processed=docs_processed, chunks_indexed=chunks_indexed)
            raise

    def _process_doc(self, conn: Connector, event: ChangeEvent) -> int:
        raw = conn.fetch_content(event.account, event.doc_id)
        content_hash = hashlib.sha256(raw.content).hexdigest()
        existing = self.metadata.get_document(event.source, event.account, event.doc_id)
        if existing and existing["content_hash"] == content_hash and existing["status"] == "indexed":
            return 0  # idempotent skip

        parsed = parse(raw, ocr_strategy=self.ocr_strategy)
        chunks = chunk_document(
            parsed, source=event.source, account=event.account,
            source_url=event.source_url, chunk_size=self.chunk_size, overlap=self.overlap,
        )
        if not chunks:
            self.metadata.upsert_document(event, content_hash=content_hash)
            return 0
        vectors = self.embedder.embed_batch([c.text for c in chunks])
        # Delete prior chunks for this doc, then add fresh.
        self.index.delete_by_doc_id(event.source, event.account, event.doc_id)
        self.index.add_batch([c.chunk_id for c in chunks], np.array(vectors, dtype=np.float32))
        self.metadata.upsert_document(event, content_hash=content_hash)
        self.metadata.upsert_chunks(chunks)
        return len(chunks)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_sync.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[SYNC] Task 11: orchestrator with per-source + per-doc isolation

- One try/except wraps per-source listing (auth errors don't poison run)
- One try/except wraps per-doc processing (bad PDF doesn't abort)
- DLQ + metadata.mark_failed for any per-doc failure
- Idempotent skip when content_hash unchanged
- Deletes flow to both metadata and vector index
- run-log start/finish via MetadataStore

Tests: 2 unit tests passing
Feature ID: 11"
```

---

## Task 12: LLM Backends (Claude CLI + Ollama)

**Files:**
- Create: `src/rag/llm.py`
- Test: `tests/unit/test_llm.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_llm.py`:

```python
from unittest.mock import patch, MagicMock
import httpx
import respx
import pytest
from rag.llm import ClaudeCLIBackend, OllamaBackend, route_query


def test_claude_cli_shells_out():
    with patch("rag.llm.subprocess.run") as run:
        run.return_value = MagicMock(stdout="Claude's answer.\n", returncode=0, stderr="")
        be = ClaudeCLIBackend()
        out = be.generate(system="sys", user="hello?")
        assert out == "Claude's answer."
        # Verify the claude CLI was invoked.
        run.assert_called_once()
        cmd = run.call_args[0][0]
        assert cmd[0] == "claude"


def test_claude_cli_propagates_failure():
    with patch("rag.llm.subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=2, stderr="auth required")
        with pytest.raises(RuntimeError, match="auth required"):
            ClaudeCLIBackend().generate(system="s", user="u")


@respx.mock
def test_ollama_backend_calls_chat_endpoint():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "Ollama's answer."}})
    )
    be = OllamaBackend(model="qwen2.5:7b", base_url="http://localhost:11434")
    assert be.generate(system="s", user="u") == "Ollama's answer."


def test_route_query_uses_private_prefix():
    claude = MagicMock(); claude.generate.return_value = "C"
    ollama = MagicMock(); ollama.generate.return_value = "O"
    text, is_private = route_query("private: my question", claude=claude, ollama=ollama,
                                   private_prefix="private:", default="claude-cli",
                                   private_routes_to="ollama")
    assert text == "my question"
    assert is_private is True


def test_route_query_default():
    claude = MagicMock(); claude.generate.return_value = "C"
    ollama = MagicMock(); ollama.generate.return_value = "O"
    text, is_private = route_query("normal question", claude=claude, ollama=ollama,
                                   private_prefix="private:", default="claude-cli",
                                   private_routes_to="ollama")
    assert text == "normal question"
    assert is_private is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_llm.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/rag/llm.py`**

```python
"""LLM generation backends. Claude Code CLI (Max auth) + Ollama local."""
from __future__ import annotations
import subprocess
from typing import Literal, Protocol
import httpx


class LLMBackend(Protocol):
    def generate(self, system: str, user: str) -> str: ...


class ClaudeCLIBackend:
    """Shells out to the Claude Code CLI. Uses the user's Max subscription auth."""

    def __init__(self, command: str = "claude", timeout: float = 120.0) -> None:
        self.command = command
        self.timeout = timeout

    def generate(self, system: str, user: str) -> str:
        prompt = f"<system>\n{system}\n</system>\n<user>\n{user}\n</user>"
        result = subprocess.run(
            [self.command, "--print", prompt],
            capture_output=True, text=True, timeout=self.timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "claude CLI failed")
        return result.stdout.strip()


class OllamaBackend:
    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 timeout: float = 120.0) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def generate(self, system: str, user: str) -> str:
        resp = self._client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


def route_query(
    raw: str,
    claude: LLMBackend,
    ollama: LLMBackend,
    private_prefix: str = "private:",
    default: Literal["claude-cli", "ollama"] = "claude-cli",
    private_routes_to: Literal["claude-cli", "ollama"] = "ollama",
) -> tuple[str, bool]:
    """Strip the private prefix if present and return (cleaned_text, is_private)."""
    if raw.lstrip().lower().startswith(private_prefix.lower()):
        return raw.lstrip()[len(private_prefix):].lstrip(), True
    return raw, False
```

**Engineer note on Claude CLI:** the actual `claude` CLI invocation flag is `--print` for non-interactive output. If your installed version differs (`claude -p`, `claude print`, etc.), adjust the `command` list and verify with `claude --help`. The wrapper's external behavior must stay identical.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_llm.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[LLM] Task 12: Claude CLI + Ollama generation backends + router

- ClaudeCLIBackend shells out to 'claude --print' (Max auth)
- OllamaBackend hits /api/chat
- route_query strips 'private:' prefix and signals routing decision

Tests: 4 unit tests passing
Feature ID: 12"
```

---

## Task 13: Query Module

**Files:**
- Create: `src/rag/query.py`
- Test: `tests/unit/test_query.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_query.py`:

```python
from unittest.mock import MagicMock
import numpy as np
from rag.query import QueryEngine
from rag.types import Answer


def test_query_returns_answer_with_citations():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]
    index = MagicMock()
    index.search.return_value = [
        ("localfs:default:doc1:00000", 0.95),
        ("localfs:default:doc2:00000", 0.80),
    ]
    metadata = MagicMock()
    metadata.hydrate_chunks.return_value = [
        {"chunk_id": "localfs:default:doc1:00000", "text": "Safety policy chunk A",
         "source_url": "file:///doc1.pdf", "page_start": 1, "page_end": 1},
        {"chunk_id": "localfs:default:doc2:00000", "text": "Safety policy chunk B",
         "source_url": "file:///doc2.pdf", "page_start": 3, "page_end": 3},
    ]
    claude = MagicMock(); claude.generate.return_value = "Drivers under 6 months..."
    ollama = MagicMock()

    qe = QueryEngine(embedder=embedder, index=index, metadata=metadata,
                     claude=claude, ollama=ollama, top_k=5,
                     private_prefix="private:", default_backend="claude-cli",
                     private_routes_to="ollama")
    answer = qe.ask("What does the safety policy say about new drivers?")
    assert isinstance(answer, Answer)
    assert "Drivers under 6 months" in answer.text
    assert len(answer.citations) == 2
    assert answer.citations[0].source_url == "file:///doc1.pdf"
    assert answer.citations[0].page == 1
    assert answer.private is False


def test_query_private_uses_ollama():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2, 0.3, 0.4]
    index = MagicMock()
    index.search.return_value = [("localfs:default:doc1:00000", 0.9)]
    metadata = MagicMock()
    metadata.hydrate_chunks.return_value = [{
        "chunk_id": "localfs:default:doc1:00000", "text": "T",
        "source_url": "file:///x", "page_start": 1, "page_end": 1
    }]
    claude = MagicMock()
    ollama = MagicMock(); ollama.generate.return_value = "Local answer."

    qe = QueryEngine(embedder=embedder, index=index, metadata=metadata,
                     claude=claude, ollama=ollama, top_k=5,
                     private_prefix="private:", default_backend="claude-cli",
                     private_routes_to="ollama")
    answer = qe.ask("private: secret question")
    assert answer.text == "Local answer."
    assert answer.private is True
    claude.generate.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_query.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/rag/query.py`**

```python
"""Query engine: embed → retrieve → hydrate → generate."""
from __future__ import annotations
from typing import Literal
import numpy as np
from rag.embedder import OllamaEmbedder
from rag.index import VectorIndex
from rag.llm import ClaudeCLIBackend, LLMBackend, OllamaBackend, route_query
from rag.metadata import MetadataStore
from rag.types import Answer, Citation

_SYSTEM_PROMPT = (
    "You are an expert assistant. Answer the question using only the supplied context. "
    "Cite specific passages by quoting brief excerpts. If the answer is not in the context, "
    "say so plainly — do not invent. Be concise."
)


class QueryEngine:
    def __init__(
        self,
        embedder: OllamaEmbedder,
        index: VectorIndex,
        metadata: MetadataStore,
        claude: LLMBackend,
        ollama: LLMBackend,
        top_k: int = 5,
        private_prefix: str = "private:",
        default_backend: Literal["claude-cli", "ollama"] = "claude-cli",
        private_routes_to: Literal["claude-cli", "ollama"] = "ollama",
    ) -> None:
        self.embedder = embedder
        self.index = index
        self.metadata = metadata
        self.claude = claude
        self.ollama = ollama
        self.top_k = top_k
        self.private_prefix = private_prefix
        self.default_backend = default_backend
        self.private_routes_to = private_routes_to

    def ask(self, question: str) -> Answer:
        cleaned, is_private = route_query(
            question, claude=self.claude, ollama=self.ollama,
            private_prefix=self.private_prefix,
            default=self.default_backend,
            private_routes_to=self.private_routes_to,
        )

        qvec = np.array(self.embedder.embed_query(cleaned), dtype=np.float32)
        hits = self.index.search(qvec, k=self.top_k)
        chunk_ids = [h[0] for h in hits]
        score_by_id = {h[0]: h[1] for h in hits}

        rows = self.metadata.hydrate_chunks(chunk_ids)
        # Preserve ranking order.
        by_id = {r["chunk_id"]: r for r in rows}
        ordered = [by_id[cid] for cid in chunk_ids if cid in by_id]

        citations = [
            Citation(
                chunk_id=r["chunk_id"],
                source_url=r["source_url"],
                excerpt=r["text"][:200],
                page=r.get("page_start"),
                score=score_by_id.get(r["chunk_id"], 0.0),
            )
            for r in ordered
        ]

        context = "\n\n".join(
            f"[Source: {r['source_url']} page {r.get('page_start')}]\n{r['text']}"
            for r in ordered
        )
        user_msg = f"Context:\n{context}\n\nQuestion: {cleaned}"

        backend: LLMBackend = (
            self.ollama if (is_private and self.private_routes_to == "ollama")
            else self.claude if self.default_backend == "claude-cli"
            else self.ollama
        )
        answer_text = backend.generate(system=_SYSTEM_PROMPT, user=user_msg)
        return Answer(text=answer_text, citations=citations, private=is_private)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_query.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "[QUERY] Task 13: query engine ties embed→retrieve→hydrate→generate

- Top-k retrieval against TurboVec
- Metadata hydration preserves ranking order
- Citation objects carry score + page
- Private prefix routes to Ollama exclusively

Tests: 2 unit tests passing
Feature ID: 13"
```

---

## Task 14: CLI

**Files:**
- Create: `src/rag/serve/__init__.py`
- Create: `src/rag/serve/cli.py`

- [ ] **Step 1: Implement the CLI**

`src/rag/serve/__init__.py`:

```python
"""Serve entry points (CLI, MCP)."""
```

`src/rag/serve/cli.py`:

```python
"""`rag` command — query, sync, status, dlq replay."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from rag.config import load_config, LocalfsSource
from rag.connectors.localfs import LocalfsConnector
from rag.dlq import DeadLetterQueue
from rag.embedder import OllamaEmbedder
from rag.index import VectorIndex
from rag.llm import ClaudeCLIBackend, OllamaBackend
from rag.metadata import MetadataStore
from rag.query import QueryEngine
from rag.sync import SyncOrchestrator

console = Console()

_INDEX_DIM = 384  # bge-small-en-v1.5


def _build(cfg_path: Path):
    cfg = load_config(cfg_path)
    meta = MetadataStore(cfg.paths.metadata)
    dlq = DeadLetterQueue(cfg.paths.dlq)
    index_path = cfg.paths.bundle_dir / "index.tq"
    index = VectorIndex.load(dim=_INDEX_DIM, path=index_path)
    embedder = OllamaEmbedder(model=cfg.embedding.model,
                              base_url=cfg.embedding.ollama_url,
                              batch_size=cfg.embedding.batch_size)
    return cfg, meta, dlq, index, embedder


@click.group()
def main() -> None:
    """Super RAG CLI."""


@main.command()
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
def sync(config: str) -> None:
    """Run a sync pass: pull deltas, parse, embed, index."""
    cfg, meta, dlq, index, embedder = _build(Path(config))
    connectors: dict = {}
    accounts: dict[str, list[str]] = {}
    for s in cfg.sources:
        if isinstance(s, LocalfsSource):
            connectors["localfs"] = LocalfsConnector(roots=s.paths)
            accounts["localfs"] = ["default"]
        # Other source kinds are added in Plan 2.
    orch = SyncOrchestrator(
        connectors=connectors, accounts_per_connector=accounts,
        embedder=embedder, index=index, metadata=meta, dlq=dlq,
        chunk_size=cfg.chunking.fallback_size, overlap=cfg.chunking.overlap,
        ocr_strategy=cfg.ocr.strategy if cfg.ocr.enabled else "never",
    )
    result = orch.run()
    index.save()
    console.print(f"[green]Sync complete[/]: processed={result.docs_processed} "
                  f"failed={result.docs_failed} chunks={result.chunks_indexed}")


@main.command()
@click.argument("question", nargs=-1, required=True)
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
@click.option("-k", "--top-k", default=5, type=int)
def query(question: tuple[str, ...], config: str, top_k: int) -> None:
    """Ask a question. Prefix with 'private:' to keep generation local."""
    q = " ".join(question)
    cfg, meta, dlq, index, embedder = _build(Path(config))
    claude = ClaudeCLIBackend()
    ollama = OllamaBackend(model=cfg.llm.ollama_model, base_url=cfg.embedding.ollama_url)
    qe = QueryEngine(
        embedder=embedder, index=index, metadata=meta,
        claude=claude, ollama=ollama, top_k=top_k,
        private_prefix=cfg.llm.private_prefix,
        default_backend=cfg.llm.default,
        private_routes_to=cfg.llm.private_tag_routes_to,
    )
    ans = qe.ask(q)
    console.rule("[bold]Answer")
    console.print(ans.text)
    console.rule("[bold]Citations")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Source"); table.add_column("Page"); table.add_column("Score")
    table.add_column("Excerpt", overflow="fold")
    for c in ans.citations:
        table.add_row(c.source_url, str(c.page or ""), f"{c.score:.3f}", c.excerpt)
    console.print(table)
    if ans.private:
        console.print("[yellow]Generated locally (private mode)[/]")


@main.command()
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
def status(config: str) -> None:
    """Show last run + DLQ counts."""
    cfg, meta, dlq, _, _ = _build(Path(config))
    runs = meta.list_runs()
    console.print(f"Total runs: {len(runs)}")
    if runs:
        last = runs[0]
        console.print(f"Last: {last['started_at']} → {last['finished_at']} "
                      f"[{last['status']}] docs={last['docs_processed']} chunks={last['chunks_indexed']}")
    dlq_count = sum(1 for _ in dlq.iter_entries())
    console.print(f"DLQ entries: {dlq_count}")


@main.group("dlq")
def dlq_group() -> None:
    """Dead-letter queue inspection and replay."""


@dlq_group.command("list")
@click.option("--config", "-c", default="config.yaml", type=click.Path(exists=True))
def dlq_list(config: str) -> None:
    _cfg, _meta, dlq, _idx, _emb = _build(Path(config))
    for e in dlq.iter_entries():
        console.print(json.dumps(e, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the CLI installs and shows help**

```bash
rag --help
rag sync --help
rag query --help
```

Expected: Click-formatted help for each command. No errors.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "[CLI] Task 14: rag command (sync, query, status, dlq)

- click-based subcommands
- _build() wires config → metadata → dlq → index → embedder
- query subcommand shows answer + citations table via rich
- status subcommand shows last run + DLQ count
- Index dim hardcoded to 384 (bge-small); revisit if model changes

Tests: command help verified manually; programmatic test in Task 15
Feature ID: 14"
```

---

## Task 15: End-to-End Integration Test

**Files:**
- Create: `tests/integration/test_e2e.py`
- Create: `tests/fixtures/e2e/` (small corpus)

- [ ] **Step 1: Build the e2e fixture corpus**

```bash
mkdir -p tests/fixtures/e2e
python -c "
import fitz
doc = fitz.open(); page = doc.new_page()
page.insert_text((72, 72),
    'Acme Trucking safety policy: drivers with under 6 months tenure must not '
    'operate vehicles after midnight without supervisor approval.')
doc.save('tests/fixtures/e2e/safety_policy.pdf'); doc.close()

doc2 = fitz.open(); p2 = doc2.new_page()
p2.insert_text((72, 72),
    'Acme Trucking dispatch manual: all loads exceeding 80,000 lbs require '
    'route review with a senior dispatcher prior to departure.')
doc2.save('tests/fixtures/e2e/dispatch_manual.pdf'); doc2.close()

print('e2e fixtures generated')
"
```

- [ ] **Step 2: Write the integration test**

`tests/integration/test_e2e.py`:

```python
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
```

- [ ] **Step 3: Run the integration test**

```bash
# Verify Ollama is running first
curl -s http://localhost:11434/api/tags | head

# Run with the flag
RAG_INTEGRATION=1 pytest tests/integration/test_e2e.py -v
```

Expected: 1 passed. If Ollama isn't running, skip is reported.

- [ ] **Step 4: Run the full unit suite to make sure nothing regressed**

```bash
pytest tests/ -v --ignore=tests/integration
```

Expected: all unit tests pass.

- [ ] **Step 5: Update `.agent/state.json` + `.agent/progress.md`**

`.agent/state.json` patch:

```json
{
  "working_directory": "C:\\Users\\jswil\\repos\\super-rag-gdrive-onedrive",
  "platform": "Cowork on Windows",
  "model": "claude-opus-4-7",
  "current_plan": "docs/superpowers/plans/2026-05-23-rag-mvp-plan.md",
  "current_task": "complete",
  "git": {"branch": "main", "last_commit": "see git log"},
  "build_status": "passing",
  "test_status": "passing (unit + e2e integration)",
  "connections": ["ollama (local)", "claude-cli (local)"],
  "handoff_notes": "Plan 1 MVP complete. Ready for Plan 2 (cloud connectors)."
}
```

Append to `.agent/progress.md`:

```markdown
## 2026-05-23 — Plan 1 complete
- All 15 tasks merged
- Unit test suite green
- E2E integration green against local Ollama
- Next: write Plan 2 (Composio-driven cloud connectors)
```

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "[E2E] Task 15: integration test + state checkpoint

- tests/integration/test_e2e.py wires sync→query via CLI runner
- Gated by RAG_INTEGRATION=1 + running Ollama
- Fixture PDFs generated in tests/fixtures/e2e/
- .agent state advanced to 'Plan 1 complete'

Tests: 1 e2e integration test, full unit suite re-verified
Feature ID: 15

[CHECKPOINT] Plan1-MVP complete"
```

---

## Plan 1 Self-Review

**Spec coverage** (each spec section → task):
- §1 Purpose → Task 1 README, 14 CLI
- §2 Goals/Non-goals → Tasks 5 (parse+OCR), 14 (CLI), 12 (Claude default + Ollama private)
- §3 Architecture → Plan 1 omits VPS/Tailscale (Plan 4); laptop-only is captured Tasks 1-14
- §4 Components → 1:1 mapping with tasks (connectors §4.1→T9-10, parser §4.2→T5, chunker §4.3→T6, embedder §4.4→T7, index §4.5→T8, metadata §4.6→T3, sync §4.7→T11, dlq §4.8→T4, query §4.9→T13, llm §4.10→T12, serve §4.11→T14)
- §5 Data flow → Task 11 implements initial ingest + delta; Plan 4 will add bundle emission/sync
- §6 Error handling → Task 11 implements per-source + per-doc isolation; per-batch retry deferred to Plan 2 (only matters with cloud connectors); retry policy and DLQ replay covered Tasks 4, 11
- §7 Testing → Tasks 2-13 each include unit tests; Task 15 covers integration; eval set deferred to Plan 3
- §8 Config → Task 2
- §9 Security → Plan 1 only writes local files; deferred encryption is Plan 4
- §10 Open questions → tracked in plan-level notes; revisit in Plan 4
- §11 Out of scope → respected

**Placeholder scan:** none found. Every step has concrete code or commands.

**Type consistency:** ChangeEvent, RawDoc, ParsedDoc, Chunk, Citation, Answer defined once in Task 3 (`types.py`), used identically in every later task. `chunk_id` format `{source}:{account}:{doc_id}:{idx:05d}` consistent across Tasks 3, 6, 8.

**Known deferrals for future plans:**
- Plan 2: Composio-driven gdrive/onedrive/gmail/outlook connectors, per-batch embedding retry, integration tests against real cloud sources
- Plan 3: MCP server (fastmcp), reranker, eval set + recall@5 measurement
- Plan 4: VPS systemd units, bundle emission + atomic swap, Tailscale + rsync + Syncthing, smoke tests, manifest SHA verification

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-rag-mvp-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
