# Super RAG — Setup Runbook

A formal, step-by-step "get up and running" guide for the local-files MVP (Phase 1).
Target: fresh Windows machine to a working `rag query` response in ~20 minutes.

All commands assume **PowerShell 7+** unless noted. Replace `C:\Users\jswil\` with your
own home path.

---

## 1. Prerequisites

Every prereq below has a verification command + expected output. Do not skip the
verifications — half of the failure modes in Section 4 come from a prereq that looks
installed but is not actually on `PATH` or not actually running.

### 1.1 Python 3.12

```powershell
choco install python --version=3.12.7 -y
```

Verify:

```powershell
python --version
# Expected: Python 3.12.x  (must start with 3.12)
```

If `python` resolves to 3.11 or 3.13, install 3.12 explicitly and use `py -3.12` for
the `uv venv` step.

### 1.2 `uv` package manager

```powershell
pip install uv
# or: irm https://astral.sh/uv/install.ps1 | iex
```

Verify:

```powershell
uv --version
# Expected: uv 0.4.x (or newer)
```

### 1.3 Ollama running on localhost:11434

```powershell
choco install ollama -y
# then launch the Ollama tray app, or:
ollama serve   # leave running in a separate terminal
```

Verify the daemon responds:

```powershell
curl http://localhost:11434/api/tags
# Expected: JSON body like {"models":[...]}  (HTTP 200)
```

### 1.4 Embedding + generation models pulled

```powershell
ollama pull bge-small-en-v1.5
ollama pull qwen2.5:7b
```

Verify both are present:

```powershell
ollama list
# Expected: rows for bge-small-en-v1.5  AND  qwen2.5:7b
```

Sanity-check the embedding endpoint returns a 384-dim vector (the code hard-codes
`_INDEX_DIM = 384` in `src/rag/serve/cli.py`):

```powershell
curl -X POST http://localhost:11434/api/embeddings `
  -H "Content-Type: application/json" `
  -d '{\"model\":\"bge-small-en-v1.5\",\"prompt\":\"hello\"}' | ConvertFrom-Json | `
  ForEach-Object { $_.embedding.Length }
# Expected: 384
```

### 1.5 Tesseract OCR

```powershell
choco install tesseract -y
```

Verify it is on `PATH`:

```powershell
tesseract --version
# Expected: tesseract v5.x.x  (plus build info)
```

### 1.6 Poppler (for `pdf2image`)

```powershell
choco install poppler -y
```

Verify:

```powershell
pdftoppm -v
# Expected: pdftoppm version 24.x  (writes to stderr — that's fine)
```

If `pdftoppm` is not found, add Poppler's `bin` directory to `PATH` (e.g.
`C:\ProgramData\chocolatey\lib\poppler\tools\Library\bin`).

### 1.7 Claude Code CLI (authenticated)

The CLI is shelled out from `src/rag/llm.py::ClaudeCLIBackend` via
`claude --print <prompt>`. It uses your Max-plan auth.

```powershell
# Install per Anthropic docs, then:
claude login
```

Verify the CLI prints a real model response:

```powershell
claude --print "Reply with the single word: pong"
# Expected: pong
```

If this prints anything other than a clean assistant response (e.g. an auth prompt,
empty string, or stack trace), the RAG `query` command will fail.

---

## 2. First-Run Setup

### 2.1 Clone and enter the repo

```powershell
git clone <repo-url> C:\Users\jswil\repos\super-rag-gdrive-onedrive
cd C:\Users\jswil\repos\super-rag-gdrive-onedrive
```

### 2.2 Create the virtualenv and install the package

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"
```

Verify the `rag` console script is installed:

```powershell
rag --help
# Expected: shows the click group with commands: sync, query, status, dlq
```

### 2.3 Copy and edit the config

```powershell
Copy-Item config.example.yaml config.yaml
```

Open `config.yaml` and confirm/edit these paths:

- `sources[0].paths` — folder(s) containing your documents
- `paths.bundle_dir` — where `index.tq` (the TurboVec vector index) is written
- `paths.dlq` — JSONL log of failed documents
- `paths.metadata` — SQLite store of runs + chunks

Create the data directories ahead of time so the first `sync` does not error:

```powershell
New-Item -ItemType Directory -Force C:\Users\jswil\rag-data\bundles | Out-Null
```

---

## 3. Smoke Test

### 3.1 Seed a minimal corpus

```powershell
New-Item -ItemType Directory -Force C:\Users\jswil\Documents\rag-test-corpus | Out-Null
@'
The safety policy requires new drivers to complete a 90-day probation period.
During probation, new drivers cannot operate vehicles after 10pm.
'@ | Set-Content C:\Users\jswil\Documents\rag-test-corpus\safety-policy.txt
```

### 3.2 Run a sync pass

```powershell
rag sync
# Expected: Sync complete: processed=1 failed=0 chunks=1  (or chunks>=1)
```

### 3.3 Confirm the index was written

```powershell
Test-Path C:\Users\jswil\rag-data\bundles\index.tq
# Expected: True
```

### 3.4 Ask a question

```powershell
rag query "what does the safety policy say about new drivers?"
# Expected: an "Answer" panel that mentions the 90-day probation,
#           followed by a "Citations" table with safety-policy.txt
```

### 3.5 Ask a private (local-only) question

```powershell
rag query "private: summarize the safety policy"
# Expected: same shape, plus a yellow "Generated locally (private mode)" footer.
#           Generation routes to Ollama qwen2.5:7b instead of the Claude CLI.
```

If both queries return reasonable text + at least one citation, the system is working.

---

## 4. Common Failure Modes & Fixes

### 4.1 Ollama not running

- **Detect:** `httpx.ConnectError: [Errno 10061] No connection could be made` on `sync` or `query`.
- **Fix:** Start Ollama (`ollama serve`, or launch the tray app). Re-run
  `curl http://localhost:11434/api/tags`.

### 4.2 Embedding model not pulled

- **Detect:** HTTP 404 from `/api/embeddings`, body like
  `{"error":"model 'bge-small-en-v1.5' not found"}`.
- **Fix:** `ollama pull bge-small-en-v1.5`.

### 4.3 Qwen model not pulled (only fails on `private:` queries)

- **Detect:** HTTP 404 from `/api/chat` mentioning `qwen2.5:7b`.
- **Fix:** `ollama pull qwen2.5:7b`.

### 4.4 Claude CLI not authenticated

- **Detect:** `RuntimeError: claude CLI failed` from `ClaudeCLIBackend.generate`, or
  `subprocess.TimeoutExpired` after 120s while the CLI sits at a login prompt.
- **Fix:** Run `claude login` once, then re-verify with
  `claude --print "ping"`. The Python wrapper only works when the CLI is fully
  non-interactive.

### 4.5 Tesseract not on `PATH`

- **Detect:** During `sync`, parsing errors like
  `pytesseract.pytesseract.TesseractNotFoundError`. Affected docs land in the DLQ.
- **Fix:** Reopen your shell after `choco install tesseract`, or set
  `$env:Path += ";C:\Program Files\Tesseract-OCR"` and verify with `tesseract --version`.

### 4.6 TurboVec install fails

- **Detect:** `uv pip install -e ".[dev]"` errors on the `turbovec` wheel
  (missing build tools, no prebuilt wheel for your Python).
- **Fix:** Confirm you are on Python 3.12 (`python --version`). If you are on 3.13+,
  TurboVec may not yet have a wheel — recreate the venv with `py -3.12 -m venv .venv`
  and reinstall. As a last resort, install the MSVC build tools
  (`choco install visualstudio2022buildtools`).

### 4.7 OCR fallback never triggers (scanned PDF returns empty text)

- **Detect:** Sync logs `chunks=0` for a known scanned PDF; querying it returns
  no citations.
- **Fix:** Confirm `ocr.enabled: true` and `ocr.strategy: auto_detect` in
  `config.yaml`. The trigger threshold is `ocr.min_chars_per_page: 100` —
  scanned pages with under 100 extracted chars route to Tesseract. Also verify
  Poppler is on `PATH` (Section 1.6); `pdf2image` silently no-ops without it.

### 4.8 Embedding dimension mismatch

- **Detect:** On `query` after switching embedding models: `ValueError: dim mismatch`
  or zero results despite a known-good corpus.
- **Fix:** `_INDEX_DIM = 384` is hard-coded for `bge-small-en-v1.5`. If you change
  `embedding.model`, you must also delete the old index and re-sync:
  ```powershell
  Remove-Item C:\Users\jswil\rag-data\bundles\index.tq
  Remove-Item C:\Users\jswil\rag-data\meta.sqlite
  rag sync
  ```

### 4.9 `config.yaml not found`

- **Detect:** Click error: `Invalid value for '--config' / '-c': Path 'config.yaml'
  does not exist`.
- **Fix:** Run `rag` from the repo root, or pass `-c C:\full\path\to\config.yaml`.

---

## 5. Daily-Use Commands

```powershell
# Pull deltas from all configured sources, parse, embed, index.
rag sync

# Ask a question (uses Claude CLI by default).
rag query "what changed in the Q2 financial summary?"

# Same, but force generation to stay local (routes to Ollama qwen2.5:7b).
rag query "private: list every customer name mentioned in last week's emails"

# Show last run + DLQ counts.
rag status

# Inspect every failed document (full JSON entries).
rag dlq list

# Override config path or top-k.
rag query -c C:\path\to\config.yaml -k 10 "..."
```

---

## 6. Where State Lives

Paths below match `config.example.yaml`. Adjust to match your `config.yaml`.

| Path | Purpose | Rebuildable? | Back up? |
|------|---------|--------------|----------|
| `C:\Users\jswil\rag-data\bundles\index.tq` | TurboVec vector index (all embeddings) | Yes — `rag sync` re-embeds everything | Optional (saves re-embedding time) |
| `C:\Users\jswil\rag-data\meta.sqlite` | SQLite: runs, docs, chunks, citations metadata | Yes — recreated by `rag sync` | Optional |
| `C:\Users\jswil\rag-data\dlq.jsonl` | Dead-letter queue: per-doc failures with reason + stack | No — historical record of failures | **Yes** |
| `config.yaml` | Source paths, model choices, routing rules | No — hand-edited | **Yes** |
| `.agent/progress.md`, `.agent/tasks.json`, `.agent/state.json` | Cross-session handoff state for the coding agent | No — manual + agent-written | **Yes** (in repo) |
| `.venv/` | Python virtualenv | Yes — `uv venv && uv pip install -e ".[dev]"` | No |
| Your source documents (`sources[*].paths`) | The corpus itself | No — these are the originals | **Yes** (separate backup; RAG never modifies them) |

**Rule of thumb:** if you lost everything except `config.yaml`, your source documents,
and `dlq.jsonl`, a single `rag sync` rebuilds the entire searchable state.

---

## 7. Cloud Sources (Drive / OneDrive / Gmail / Outlook via Composio)

Cloud connectors fetch documents through [Composio](https://composio.dev). They are
optional — a localfs-only setup ignores all of this.

### 7.1 Install the cloud extra

```powershell
uv pip install -e ".[dev,cloud]"   # adds the `composio` SDK
```

### 7.2 Connect your accounts + get an API key

1. In Composio, connect each Google Drive / OneDrive / Gmail / Outlook account you want
   indexed. Each connection has an **account ID** (e.g. `googledrive_xxxx`,
   `one_drive_xxxx`, `gmail_xxxx`, `outlook_xxxx`).
2. Get your Composio **API key** and export it (the env var name must match
   `composio.api_key_env` in config, default `COMPOSIO_API_KEY`):

   ```powershell
   $env:COMPOSIO_API_KEY = "your-key"      # this shell only; set permanently via setx
   ```

### 7.3 Configure sources

In `config.yaml`, add a `composio:` block mapping aliases → account IDs, then add
`sources` entries that reference those aliases (see `config.example.yaml` for the shape):

```yaml
composio:
  api_key_env: COMPOSIO_API_KEY
  connected_accounts:
    personal-jeremy: googledrive_xxxx
    work-dobeu: outlook_xxxx

sources:
  - kind: localfs
    paths: [C:\Users\jswil\Documents\rag-test-corpus]
  - kind: gdrive
    accounts: [personal-jeremy]
    mime_filter: [application/pdf]
  - kind: outlook
    accounts: [work-dobeu]      # no mime_filter — see note below
```

### 7.4 Sync and query

```powershell
rag sync                        # now also pulls Drive/OneDrive/Gmail/Outlook deltas
rag query "what was in the April Twilio invoice?"
```

Cloud docs are downloaded via short-lived presigned URLs, parsed exactly like local
files, and cited back with their `webViewLink` / `webUrl` (email attachments cite the
message permalink). Per-account auth failures are isolated — one expired connection
skips that account without aborting the run; failures land in the DLQ (`rag dlq list`,
`rag dlq replay`).

### 7.5 Gotchas (verified against the live API)

- **Outlook: don't set `mime_filter`.** Microsoft Graph reports many attachments
  (including PDFs) as `application/octet-stream`, so a mime filter silently drops them.
  Omit it; the parser dispatches by content. (Gmail reports real mime types, so a Gmail
  `mime_filter` is fine.)
- **First Gmail sync on a huge mailbox is expensive.** Every `has:attachment` message is
  hydrated with its own API call to read attachment IDs. Start with a small/secondary
  account; subsequent syncs are incremental via the last-run watermark.
- **Native Google Docs/Sheets/Slides** are exported to PDF by Composio on download
  (they have `size=null`); they index fine as PDFs.

## 8. What to Run Next

- Full test suite: `pytest` (unit tests are hermetic; integration tests are gated by
  `-m integration` and require a live Ollama + `claude` CLI).
- Lint: `ruff check src tests`.
