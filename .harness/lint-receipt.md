# Ruff remediation receipt

## Scope

- Roadmap `4f1ad0998c3f` was approved on November 17, 2026. The worktree is `/Users/amywilliams/worktrees/super-rag-mcp/t3-4ef45879-4892ee7dfe04a4cf`.
- Branch `chore/wave1-api-lane-launch`, starting and ending HEAD `6be8e4d3a16ebff08e5b30292d29c95392bf3d7b`.
- The code patch is relative to the working files at lane start. It contains 24 Python files, 63 insertions and 30 deletions. This receipt is the only new file in the Git working-tree status. [Lint-only patch](../.venv/lint-remediation.8kVLVj/lint-remediation.patch)
- The scope check confirmed the pre-existing working-tree changes, including the exporter return annotation and folder-name fix, were preserved. The Ruff configuration, dependencies, workflow, test assertions and skip conditions retain their existing settings. [Scope verification](../.venv/lint-remediation.8kVLVj/scope-check.log)

Evidence links into `.venv` are machine-local logs, excluded from Git and unavailable in fresh checkouts. Results and commands are recorded here for portable review.

## Before and after

All runs used the existing CPython 3.12.15, Ruff 0.17.5 and pytest 9.2.0 in `.venv`. Both configured commands ran from this worktree with `NLTK_DATA="$PWD/.venv/nltk_data"` and `TIKTOKEN_CACHE_DIR="$PWD/.venv/tiktoken"` exported.

| Phase | Configured command | Exit | Result | Log |
| --- | --- | ---: | --- | --- |
| Before | `.venv/bin/ruff check .` | 1 | 43 findings | [Ruff before](../.venv/lint-remediation.8kVLVj/ruff-before.log) |
| Before | `.venv/bin/python -m pytest tests/unit -q` | 0 | 98 passed, 1 skipped, 53 warnings in 1.55s | [Unit before](../.venv/lint-remediation.8kVLVj/unit-before.log) |
| After | `.venv/bin/ruff check .` | 0 | 0 findings. Ruff printed `All checks passed!` | [Ruff after](../.venv/lint-remediation.8kVLVj/ruff-after.log) |
| After | `.venv/bin/python -m pytest tests/unit -q` | 0 | 98 passed, 1 skipped, 53 warnings in 1.10s | [Unit after](../.venv/lint-remediation.8kVLVj/unit-after.log) |

The before run with `--output-format concise` exited 1 and matched the previous `.venv/final-ruff.log` byte for byte. The after run with `-rs` exited 0 and identified the missing `tests/fixtures/scanned.pdf` fixture as the reason for the OCR skip. [Exact baseline findings](../.venv/lint-remediation.8kVLVj/ruff-before-concise.log) · [Skip details](../.venv/lint-remediation.8kVLVj/unit-after-skip-details.log)

A separate before-and-after probe exited 0. It confirmed matching Pydantic schemas and serialized results across all five source kinds, including an existing model instance. An uneven TurboVec result retained the existing shortest-row truncation. The exporter produced the same exit and dry-run output for a synthetic skill. [Probe script](../.venv/lint-remediation.8kVLVj/behavior-probe.py) · [Probe output](../.venv/lint-remediation.8kVLVj/behavior-probe.log)

## Code file scope

| Path | Baseline findings addressed |
| --- | --- |
| `agent-skill-bridge/scripts/export_skills.py` | `RUF059` × 1 |
| `src/rag/chunker.py` | `I001` × 1 |
| `src/rag/config.py` | `E702` × 1, `UP007` × 1 |
| `src/rag/connectors/__init__.py` | `I001` × 1, `UP035` × 1 |
| `src/rag/connectors/localfs.py` | `F401` × 1, `I001` × 1, `UP035` × 1 |
| `src/rag/dlq.py` | `I001` × 1, `UP035` × 1 |
| `src/rag/embedder.py` | `I001` × 1 |
| `src/rag/index.py` | `B905` × 1, `UP037` × 1 |
| `src/rag/llm.py` | `I001` × 1 |
| `src/rag/metadata.py` | `I001` × 1 |
| `src/rag/parser.py` | `I001` × 2 |
| `src/rag/query.py` | `UP037` × 3 |
| `src/rag/types.py` | `F401` × 1, `I001` × 1 |
| `tests/conftest.py` | `I001` × 1 |
| `tests/integration/test_e2e.py` | `I001` × 1 |
| `tests/unit/test_config.py` | `I001` × 1 |
| `tests/unit/test_dlq.py` | `F401` × 1, `I001` × 1 |
| `tests/unit/test_embedder.py` | `I001` × 1 |
| `tests/unit/test_index.py` | `F401` × 1, `I001` × 1 |
| `tests/unit/test_llm.py` | `E702` × 4, `I001` × 1 |
| `tests/unit/test_localfs.py` | `I001` × 1 |
| `tests/unit/test_metadata.py` | `I001` × 1 |
| `tests/unit/test_parser.py` | `I001` × 1 |
| `tests/unit/test_query.py` | `E702` × 2, `F401` × 1, `I001` × 1 |

The fixes sort imports, remove unused imports and the unused exporter binding, use Python 3.12 typing syntax, split statements across lines and make the existing `zip` behavior explicit with `strict=False`. The OCR imports remain inside the OCR function. The patch passed `git apply --check --reverse` and the working-tree diff passed `git diff --check`.

## Handoff

Independent review is pending. This receipt covers local lint and unit verification. Live integration and GitHub CI are pending.
