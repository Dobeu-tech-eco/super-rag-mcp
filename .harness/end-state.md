# End state: Super RAG (MVP 3)

- rounds: 1
- clarity: 80
- threshold: 80
- thresholdSource: default
- roster: codex
- status: approved
- continuedAnyway: no

Jeremy via Chester approved the end state and setup scaffold on November 17, 2026. Jeremy via Chester separately approved roadmap `4f1ad0998c3f` at 19:12 ET for baseline verification, status reconciliation and evidence-led fixes. The clarity value is a planning estimate.

## Deploy
```
deploy:
  provider: none
  productionUrl: null
  checkCommand: null
```
No deploy or live verification authorized in this lane.

## Related repos
| url | role | tag | note |
|---|---|---|---|
| Dobeu-tech-eco/dobeu-knowledge-pilot | potential future source folded into Super RAG | context | Future gated scope only; no access, migration or changes authorized here. |

## Other harnesses
| folder | decision |
|---|---|
| .agent | coexist |
| .superpowers | coexist |

## Skills
| skill | source | installed | serves component | phase | order |
|---|---|---|---|---|---|
| code-review | mattpocock/skills | yes | harness | review | 1 |

## Topology
Existing Python CLI and optional MCP server over sync/query orchestration, local/cloud connectors, parsing/chunking, Ollama embeddings, TurboVec and SQLite. This wave verifies and reconciles the existing product.

## Blueprint
| layer | choice | status |
|---|---|---|
| data model | existing SQLite metadata and TurboVec index; unchanged except evidenced defects | built |
| api surface | existing Click CLI and FastMCP tools | built |
| screens/routes | no web UI | n/a |
| auth | existing HTTP bearer token and private query routing | built |
| infra/deploy | local only; deployment excluded | n/a |
| observability | existing status and DLQ | built |
| background jobs | existing explicit sync | built |

## Sections
| # | section | serves component | files / area | depends on | complexity | status |
|---|---|---|---|---|---|---|
| 1 | Baseline verification | existing product | src/rag, tests, pyproject.toml, .github/workflows | - | normal | done |
| 2 | Status reconciliation | product documentation | README.md, CHANGELOG.md, docs, .harness | 1 | mechanical | done |
| 3 | Evidence-led fixes | existing product | src/rag, tests; agent-skill-bridge only for confirmed review findings | 1 | normal | independent review pending |

## Production readiness
appType: cli

| row | kind | evidence | status |
|---|---|---|---|
| ci | gate | .github/workflows/ci.yml | todo |
| release | gate | semver tag and changelog entry | todo |
| install-docs | gate | install, usage and exit codes in the README | todo |
| package-metadata | gate | name, version, license and entry point in the manifest | todo |
| runbook | gate | RUNBOOK.md | n/a |
| error-tracking | gate | ops/monitoring.md names the tool and where the DSN lives | n/a |
| uptime-check | gate | ops/monitoring.md names one check on a key route | n/a |
| alert-route | gate | ops/monitoring.md names who is paged and how | n/a |
| backups | gate | ops/backups.md schedule | n/a |
| restore-test | gate | ops/backups.md dated restore test | n/a |
| migration-safety | gate | expand/contract plan for schema changes | n/a |
| credential-handoff | gate | ops/credential-handoff.md | n/a |
| rollback | gate | ops/rollback.md | n/a |
| post-deploy-watch | gate | ops/rollback.md watch window | n/a |
| promotion | gate | ops/release.md preview, staging, production | n/a |
| feature-flag-hook | gate | ops/release.md flag hook for risky work | n/a |
| coverage | report | coverage percentage | todo |
| a11y-axe | report | axe violations count | n/a |
| lighthouse | report | Lighthouse scores | n/a |
| sast-semgrep | report | semgrep findings count | todo |
| license-check | report | dependency license summary | todo |
| sbom | report | SBOM file path | todo |
| stride | report | STRIDE notes | n/a |

## Goal
Establish fresh local evidence for the working MVP 3 product, reconcile status against v0.3.0 and current source, and repair only reproduced or concretely demonstrated defects. Super RAG remains the designated future fold target for dobeu-knowledge-pilot.

## Constraints
- This exact repository/worktree only; HELD and hands-off repos excluded.
- PRs stop at merge gate: no merges, deploys, archival or deletion.
- Roadmap approval covers local work through handoff for parent review. Commits, pushes and PR creation remain outside this lane.
- Codex API Burn lane only; do not substitute providers or claim unverified billing.
- Preserve existing .agent and .superpowers state; reconcile history in current documentation.

## Non-goals
- Executing or inspecting the knowledge-pilot fold, new product features, other-repo changes, release or production certification.

## Acceptance criteria
### Baseline verification
- [x] Record exact HEAD, environment, lint and unit commands, exits and failures; distinguish integration prerequisites from executed checks.
### Status reconciliation
- [x] Current product documentation distinguishes shipped v0.3.0 features, historical evidence, current verification and future gated fold.
### Evidence-led fixes
- [ ] Each fix has a concrete reproduction or source proof, focused validation and independent review; if no defects remain, record that with evidence.
- [ ] PR handoff preserves merge and deploy gates.

## Assumptions
- Existing architecture is retained; no new deploy target is required.
- The [receipt](receipt.md) distinguishes local unit evidence from historical and live verification.

## Open questions
- Parent independent review and the repository's CI and release gates remain open.
