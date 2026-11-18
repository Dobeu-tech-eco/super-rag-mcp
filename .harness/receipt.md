# Wave 1 verification receipt

## Scope and approval

- Jeremy via Chester approved roadmap `4f1ad0998c3f` on 2026-11-17 at 19:12 ET.
- Worktree `/Users/amywilliams/worktrees/super-rag-mcp/t3-4ef45879-4892ee7dfe04a4cf`, branch `chore/wave1-api-lane-launch`.
- Starting and ending HEAD `6be8e4d3a16ebff08e5b30292d29c95392bf3d7b`. This includes the v0.3.0 release commit `9f6dce007caaa41a3aae69ee4f6018dd9397a3a1`, the exporter commit `6081117`, and Dependabot configuration in `6be8e4d`. The working tree already contained the approved scaffold and local ignore rules. The v0.3.0 version is recorded in the release commit, manifest and changelog. The local clone has no v0.3.0 tag.
- The parent recorded approval in the ignored `.claude/settings.local.json` and reports T3 capabilities confirmed `codex-api-burn` routing. Billing verification is outside this receipt.
- `Dobeu-tech-eco/super-rag-mcp` remains PROTECTED in the organization. This lane ends at uncommitted changes for parent review. Commits, pushes, PR creation, merges, deployments, moves, archives, release tags and the knowledge-pilot fold remain outside this lane.

## Environment and checks

Local macOS 27.3 arm64, uv 0.13.0, CPython 3.12.15 in the ignored `.venv`, pytest 9.2.0 and Ruff 0.17.5. The system Python 3.15 was bypassed. Pytest and CLI smoke commands used worktree-local cache settings `NLTK_DATA="$PWD/.venv/nltk_data"` and `TIKTOKEN_CACHE_DIR="$PWD/.venv/tiktoken"`.

| Check | Command | Exit | Result |
| --- | --- | ---: | --- |
| Local Python environment | `uv --no-cache venv --python 3.12 --offline .venv` | 0 | Used the installed 3.12.15 interpreter |
| Baseline editable install | `uv --no-cache pip install --python .venv/bin/python -e '.[dev,mcp]'` | 0 | Resolved MCP SDK 2.3.0 under the original metadata |
| Baseline lint | `.venv/bin/ruff check . --output-format concise` | 1 | 43 findings |
| Baseline unit | `.venv/bin/python -m pytest tests/unit -q --basetemp=.venv/pytest-baseline` | 1 | 95 passed, 1 failed, 1 skipped, 53 warnings |
| Focused reproduction before fixes | `.venv/bin/python -m pytest tests/unit/test_export_skills.py tests/unit/test_mcp_app.py -q --basetemp=.venv/pytest-focused-red` | 1 | 3 failed, 6 warnings |
| Editable reinstall after bound | `uv --no-cache pip install --python .venv/bin/python -e '.[dev,mcp]'` | 0 | Resolved MCP SDK 1.30.0 |
| Focused verification after fixes | `.venv/bin/python -m pytest tests/unit/test_export_skills.py tests/unit/test_mcp_app.py -q --basetemp=.venv/pytest-focused-green` | 0 | 3 passed, 6 warnings |
| Final unit | `.venv/bin/python -m pytest tests/unit -q --basetemp=.venv/pytest-final` | 0 | 98 passed, 1 skipped, 53 warnings |
| Initial post-fix lint | `.venv/bin/ruff check . --output-format concise` | 1 | Same 43 findings with identical output |
| Package metadata check | `uv --no-cache pip check --python .venv/bin/python` | 0 | All installed packages compatible |
| Installed entry points | `.venv/bin/rag --help` and `.venv/bin/rag-mcp --help` | 0 | Both displayed usage |

The raw unit and Ruff logs and the final package freeze are in the ignored `.venv/`. The lint findings include import ordering, unused imports and one unused exporter binding. The CI scaffold runs the same repository-wide Ruff check, and subsequent remediation passes with zero findings; see lint-receipt.md. The earlier failing result above is historical baseline evidence.

## Defects verified locally

| Finding | Reproduction | Scoped change and validation |
| --- | --- | --- |
| MCP app failed to register tools after a fresh install | `test_build_app_registers_four_tools` raised `ModuleNotFoundError` from `mcp.server.fastmcp` with SDK 2.3.0 | Set `mcp>=1.30.0,<2` to keep the v1 API used by the application. The same four-tool registration test passed on 1.30.0. |
| Exporter `classify` omitted its return type | `test_classify_declares_its_return_type` resolved no return annotation | Declared `tuple[str, str, str, int, str]` for the existing five fields. The same check passed. |
| Exported folder names could keep a trailing dot | `test_safe_dirname_trims_trailing_dots_and_whitespace_before_deduplication` returned a name ending in a dot when Unicode whitespace followed dots | Trim the trailing run of dots and whitespace before deduplication. The collision and empty-result fallback assertions passed. |

The README, changelog, architecture, setup and MCP guidance now distinguish released behavior, earlier live checks and this local baseline. The docs describe full sync as bypassing the watermark while retaining the existing content-hash check.

## Limits and handoff

- The OCR unit test skipped because the repository does not include `tests/fixtures/scanned.pdf`. The unit runs emitted dependency and datetime deprecation warnings.
- The end-to-end test requires `RAG_INTEGRATION=1` and a running Ollama with `bge-small-en-v1.5` and `qwen2.5:7b` for its private query. The default Claude path would require authenticated `claude`. Live Composio checks would require the cloud extra, credentials and connected accounts. Live services, OCR integration, Docker, GitHub CI, standalone build and typecheck were outside the executed checks.
- **Independent review is pending.** The parent should review this worktree's changes, the focused failures and the subsequent passing Ruff remediation before any PR work.
- The rollback reference is the starting HEAD and existing uncommitted scaffold recorded above. A rollback of this lane should reverse only this lane's diff and retain the pre-existing scaffold and local approval.

## Review corrections and current verification

Independent review requested five corrections: SDK minimum, stale lint evidence, recovery guidance, local-only evidence links, and top_k release history. All were addressed locally. The supported SDK range is now `mcp>=1.30.0,<2`; 1.30.0 is the verified minimum, not a claim about the earliest compatible SDK. On that exact installed version, `.venv/bin/ruff check .` passed and `.venv/bin/python -m pytest tests/unit -q` passed with 99 passed, 1 skipped, 53 warnings, using the cache environment above. The additional test constructs the read-only HTTP app and verifies its three tools; the existing registration test covers four tools with sync enabled. `git diff --check` passed. Independent recheck remains pending. No hosted CI or live service verification is claimed.

## Final review disposition

Independent review and recheck accepted the code changes, SDK minimum, lint remediation and evidence corrections. The final recheck identified the required `index.tq.idmap.json` backup sidecar; the parent added it to the backup table and consistent three-file restore instructions, checked directly against `VectorIndex.load`. This last documentation correction has parent source review, not a third delegated review. Current local result: 99 passed, 1 skipped, Ruff zero findings. Hosted CI and live checks remain unverified. PR handoff is authorized by the user; merges, deployments, moves and archival remain prohibited.

Pre-commit companion was installed and read. Its Husky/npm/Prettier setup does not match this Python-only project; no Node tooling was introduced. Existing Ruff, pytest and diff checks serve as the pre-commit validation.
