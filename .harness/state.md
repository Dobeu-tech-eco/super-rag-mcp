# Harness state

## Decisions
- 2026-11-17 Jeremy via Chester approved the end state and setup scaffold. At 19:12 ET Jeremy via Chester approved roadmap `4f1ad0998c3f` for baseline verification, status reconciliation and evidence-led fixes.
- 2026-11-17 .agent and .superpowers: coexist; preserve contents.
- 2026-11-17 The parent reports T3 capabilities confirmed `codex-api-burn` routing. The earlier local CLI subscription observation was separate. Billing evidence is outside this check.
- 2026-11-17 The parent recorded approval in `.claude/settings.local.json`. The file is present and ignored by Git.
- 2026-11-17 `Dobeu-tech-eco/super-rag-mcp` remains PROTECTED in the organization. Repository moves, archives, deployments and merges are outside this lane.

## Open items
- Independent review accepted exporter, lint, SDK floor, and evidence corrections. Final backup-sidecar documentation correction was checked against VectorIndex.load by the parent. See [receipt.md](receipt.md) for the red and green checks.
- Ruff baseline had 43 findings; remediation now passes with zero findings. The scaffold runs the same lint command in CI. Typecheck and standalone build commands remain unset.
