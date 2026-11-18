# Review checklist

- Correctness: preserve sync/query contracts, stable chunk identifiers and delete propagation.
- Types: preserve Python 3.12 annotations and structured MCP outputs.
- Tests: focused regression for each evidenced defect; distinguish unit from live integration proof.
- Security: preserve private query routing, bearer-token fail-closed HTTP and read-only default.
- Conventions: CLAUDE.md, Ruff and dependency-injected handlers.
- Scope: approved three sections only; no fold, other repos, merge, deployment or deletion.
