# Plan 1 git bootstrap — run once from PowerShell at repo root.
# Usage: .\init-git.ps1
#
# Why this exists: the FUSE mount used by Cowork on Windows blocks writes to
# `.git/` from the Linux sandbox, so all per-task git commits were deferred to
# this script. This makes 15 commits in plan order so the history mirrors the
# task list in `.agent/tasks.json`.
#
# After this script:
#   uv venv
#   uv pip install -e ".[dev]"
# to create a Windows-native venv.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".venv") {
    Write-Host "Removing Linux .venv (not usable on Windows)..."
    Remove-Item -Recurse -Force ".venv"
}

if (-not (Test-Path ".git")) {
    git init -b main
} else {
    Write-Host ".git already exists, skipping init"
}

git config user.email "jswilliamstu@gmail.com"
git config user.name "Jeremy Williams"

$env:GIT_AUTHOR_NAME     = "Jeremy Williams"
$env:GIT_AUTHOR_EMAIL    = "jswilliamstu@gmail.com"
$env:GIT_COMMITTER_NAME  = "Jeremy Williams"
$env:GIT_COMMITTER_EMAIL = "jswilliamstu@gmail.com"

function Commit-Stage {
    param(
        [string[]]$Paths,
        [string]$Message
    )
    foreach ($p in $Paths) {
        if (Test-Path $p) {
            git add -- $p | Out-Null
        }
    }
    # Capture staged file count
    $staged = (git diff --cached --name-only).Count
    if ($staged -eq 0) {
        Write-Host "  (nothing staged for: $Message — skipping)"
        return
    }
    git commit -m $Message | Out-Null
    $sha = (git rev-parse --short HEAD)
    Write-Host "  $sha  $Message"
}

Write-Host ""
Write-Host "=== Replaying Plan 1 commits ==="
Write-Host ""

# Task 1 — scaffold
Commit-Stage `
    @(".gitignore", "pyproject.toml", "ruff.toml", "README.md",
      "src/rag/__init__.py",
      "src/rag/connectors", "src/rag/serve",
      "tests/__init__.py", "tests/unit/__init__.py", "tests/integration/__init__.py",
      "tests/fixtures",
      ".agent/progress.md", ".agent/tasks.json", ".agent/state.json",
      "init-git.ps1") `
    "[SCAFFOLD] Task 1: project skeleton, deps, agent state`n`nFeature ID: 1"

# NOTE: src/rag/connectors and src/rag/serve subdirectories were staged above,
# which already pulled in their __init__.py + child modules. The following
# commits add file-level granularity for the rest of the modules.

# Task 2 — config
Commit-Stage `
    @("src/rag/config.py", "tests/unit/test_config.py", "config.example.yaml") `
    "[CONFIG] Task 2: pydantic config schema + YAML loader`n`nFeature ID: 2"

# Task 3 — metadata + types
Commit-Stage `
    @("src/rag/types.py", "src/rag/metadata.py",
      "tests/conftest.py", "tests/unit/test_metadata.py") `
    "[META] Task 3: SQLite metadata store + shared types`n`n(mark_failed fix: use cur.rowcount instead of cumulative total_changes)`n`nFeature ID: 3"

# Task 4 — DLQ
Commit-Stage `
    @("src/rag/dlq.py", "tests/unit/test_dlq.py") `
    "[DLQ] Task 4: append-only JSONL dead-letter queue`n`nFeature ID: 4"

# Task 5 — parser + OCR
Commit-Stage `
    @("src/rag/parser.py", "tests/unit/test_parser.py",
      "tests/fixtures/text.pdf", "tests/fixtures/sample.docx", "tests/fixtures/sample.txt") `
    "[PARSE] Task 5: PDF + DOCX + TXT parser with OCR fallback`n`nFeature ID: 5"

# Task 6 — chunker
Commit-Stage `
    @("src/rag/chunker.py", "tests/unit/test_chunker.py") `
    "[CHUNK] Task 6: sentence-aware chunker with page-range derivation`n`nFeature ID: 6"

# Task 7 — embedder
Commit-Stage `
    @("src/rag/embedder.py", "tests/unit/test_embedder.py") `
    "[EMBED] Task 7: Ollama HTTP embedder`n`nFeature ID: 7"

# Task 8 — index
Commit-Stage `
    @("src/rag/index.py", "tests/unit/test_index.py") `
    "[INDEX] Task 8: TurboVec IdMapIndex wrapper`n`n(wrapper internals adapted to real turbovec API: add_with_ids, prepare(), dim multiple-of-8, sidecar id-map)`n`nFeature ID: 8"

# Task 9 — connector protocol
Commit-Stage `
    @("src/rag/connectors/__init__.py") `
    "[CONN] Task 9: Connector Protocol + error taxonomy`n`nFeature ID: 9"

# Task 10 — localfs
Commit-Stage `
    @("src/rag/connectors/localfs.py", "tests/unit/test_localfs.py") `
    "[LOCALFS] Task 10: filesystem connector with delete detection`n`nFeature ID: 10"

# Task 11 — sync
Commit-Stage `
    @("src/rag/sync.py", "tests/unit/test_sync.py") `
    "[SYNC] Task 11: orchestrator with per-source + per-doc isolation`n`n(VectorIndex + OllamaEmbedder moved under TYPE_CHECKING to keep collection import clean)`n`nFeature ID: 11"

# Task 12 — llm
Commit-Stage `
    @("src/rag/llm.py", "tests/unit/test_llm.py") `
    "[LLM] Task 12: Claude CLI + Ollama generation backends + router`n`nFeature ID: 12"

# Task 13 — query
Commit-Stage `
    @("src/rag/query.py", "tests/unit/test_query.py") `
    "[QUERY] Task 13: query engine ties embed-retrieve-hydrate-generate`n`nFeature ID: 13"

# Task 14 — cli
Commit-Stage `
    @("src/rag/serve/__init__.py", "src/rag/serve/cli.py") `
    "[CLI] Task 14: rag command (sync, query, status, dlq)`n`nFeature ID: 14"

# Task 15 — e2e + checkpoint
Commit-Stage `
    @("tests/integration/test_e2e.py", "tests/fixtures/e2e") `
    "[E2E] Task 15: integration test + state checkpoint`n`nFeature ID: 15`n`n[CHECKPOINT] Plan1-MVP complete"

# Final sweep — anything left over (cached, deleted, etc.)
git add -A
$leftover = (git diff --cached --name-only).Count
if ($leftover -gt 0) {
    git commit -m "[SWEEP] Plan 1: residual artifacts (caches, leftovers)" | Out-Null
    Write-Host "  swept $leftover residual file(s)"
}

Write-Host ""
Write-Host "=== Done ==="
Write-Host ""
git log --oneline
Write-Host ""
Write-Host "Next: uv venv && uv pip install -e '.[dev]'"
Write-Host ""
Write-Host "To run the unit suite on Windows:"
Write-Host "  .venv\Scripts\pytest tests\ --ignore=tests\integration -v"
Write-Host ""
Write-Host "To run the E2E test (requires Ollama + bge-small-en-v1.5 + qwen2.5:7b):"
Write-Host "  `$env:RAG_INTEGRATION = '1'; .venv\Scripts\pytest tests\integration -v"
