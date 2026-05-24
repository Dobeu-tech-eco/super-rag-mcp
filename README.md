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
