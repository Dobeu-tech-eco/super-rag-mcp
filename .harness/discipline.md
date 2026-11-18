# Harness discipline (Rule 8)

Read by lead, builder, reviewer and verifier. Copied to `.harness/discipline.md` at scaffold.

1. **Define done first.**
   Where it bites: the plan checkpoint will not open without a Done section: outcome plus check method (tests, visual, source, review). Lead refuses to plan without it.
2. **End with a receipt.**
   Where it bites: `receipt.md` lists tests run with pass/fail counts, review verdict, approver, steps outside the change, open risks, rollback point. Shown at the ship checkpoint and appended to the PR body.
3. **Cap fix rounds at five.**
   Where it bites: in `run` and per builder. After five rounds (1-3 Sonnet resuming the same worker, 4-5 a fresh worker one tier up on Opus), stop and escalate with what failed; the escalation goes into `.harness/state.md`. On hitting the hard round-5 cap with bugs still failing, first auto-run a fresh `/diagnosing-bugs` pass (`npx skills add https://github.com/mattpocock/skills --skill diagnosing-bugs`) on everything still failing (upstream renamed `diagnose` to `diagnosing-bugs`, so the hard cap reruns that skill from scratch, not the round-2 output), apply its findings, and only then escalate to the user with what still fails.
4. **Repeat mistake becomes a check.**
   Where it bites: `learn` detects a lesson seen twice (same normalized text or same file+rule) and offers to promote it: a line in `.harness/checks.sh` (run by the Stop hook), a test skeleton in the repo's test dir, or a line in `review-checklist.md`. It records "lives at <path>" in `lessons.md`.
5. **State outside the chat.**
   Where it bites: `.harness/state.md` holds decisions, failures and open items, appended by run and learn, and read at session start by `session-lessons.sh`. The file is the record.
6. **Auto-add the receipt.**
   Where it bites: `hooks/pr-receipt.sh` runs on `gh pr create` and `gh pr edit`. If the PR body lacks `## Change receipt`, it edits it in, and it adds or extends the PR template in the same branch when neither the repo nor the org default has the section.
7. **Auto hand-off on stall.** If the lead hits a usage or token limit, or goes unresponsive on a thread, immediately write the handoff (handoff-write.py) and fail over to the next eligible lead provider (failover.py `next_lead`, honoring `lead_provider`). Record the hand-off and the provider switch in the receipt. Never drop the thread silently.

## Push exception

Agents never push. The one exception is `pr-receipt.sh`, which pushes only the PR's own branch, and only to add or extend the PR template. It never pushes any other branch.

## Rule 9 — Orchestration (frontier for advice and sign-off, execution on the cheapest capable tier)

Applies to every agent provider the roster can dispatch; the lead is the session running `run`.

1. **Lead thinks, workers type.** The lead (frontier tier) decomposes, writes briefs, merges and verifies. It never implements a builder section itself except a trivial single-file change under ~20 lines.
2. **Frontier is for advice and sign-off only.** The frontier tier runs the lead (planning), the axis-scaled reviewers' final whole-diff review, and the verifier. Execution — every builder — never runs a frontier model; it takes the cheapest capable model and raises effort (low/medium/high/max) for harder lanes. Every dispatch names both a model and an effort. A builder dispatched on a frontier model is a defect the final review blocks on.
3. **Parallel by file set.** Independent builders run in one dispatch message. Two writers never share a file, section or tree.
4. **Briefs, not history.** A worker receives its plan section (goal, owned files, read-only files, acceptance criteria, lessons, test command, commit message, report path) and nothing else. It returns status, commit, a one-line test summary and concerns.
5. **Worker contract.** A worker never pushes, never spawns subagents or reviewers, never grades its own work, never edits outside its file set, and stops to report when the plan is wrong instead of improvising.
6. **Fix loop inside the cap.** Rounds 1–3 resume the same worker (round 2 first runs `/diagnosing-bugs` on the failure and pastes its root cause into the brief); rounds 4–5 go to a fresh worker one tier up (economy→standard, or one effort level higher when already on standard); after round 5 the lead stops and escalates (Rule 8.3). Three materially identical failures mean the approach is wrong, not the retry count.
7. **Rulings are written down.** Every decision the lead makes without the user goes to `.harness/state.md` → `## Decisions` as `Ruling: <what> — <why> — <cost if wrong>`. After a context reset the lead trusts `state.md` and `git log`, never memory, and never re-dispatches a builder whose section is marked done.
8. **Hard stops.** The lead asks before: pushing, merging to the default branch, publishing, deploying, purchasing, deleting data or branches, touching credentials, or when the plan is broken enough that every path is a guess. Everything else it rules on and continues.
9. **Scope before spend.** A run checks its scope first (workspace root, member repo, single, none) and pivots to the workspace root when it is inside a member repo. A context spike before the plan checkpoint is a stop signal: stop every agent, write state, re-run setup, resume. Never push through it.
10. **Never idle, never collide.** While any ready section with a non-overlapping file set exists, a builder is working on it. A stalled builder is parked with an action item and the next ready section is dispatched in the same step; the run ends only when nothing is ready or at a checkpoint. Two writers never share a file, even to stay busy.
11. **Effort before escalation.** To do more without spending more, raise a cheaper model's effort before reaching for a pricier model or tier.
12. **The lead provider is selectable.** The provider that fills the lead, advisory and sign-off seats is chosen with `/dt:model` (default Claude, stored as `lead_provider`), but the frontier-only-for-advice-and-sign-off rule holds whichever provider leads; execution seats are never affected. Changing the lead copies the orchestrator's current `dt@dts2` plugin and skill list into that agent's backend (`scripts/lead_skills.py`) so it can run `/dt`. A non-lead may stay on an older install until setup, onboard, or that switch.
13. **Partial output is not done.** An agent that hits its turn cap returns a first report line `PARTIAL: hit turn cap at <step>`. The head or lead treats any report carrying it as unfinished: never mark the section done or count a verdict as passed, then re-dispatch with a narrower scope (the remaining steps only) or a fresh agent, inside the Rule 9.6 fix-loop cap.
14. **One model per agent session.** A session keeps the model it started on, including when it is resumed; to change model, start a fresh worker (fix rounds 1-3 on Sonnet, rounds 4-5 on Opus).

## Rule 10 — Branches, worktrees and pull requests

1. **One run, one branch.** `run` creates `dts2/<stamp>/main` from the current branch and all builder work lands there. The default branch is never a run's working branch.
2. **One builder, one worktree (git).** In a git repo each builder gets `git worktree add ../<repo>-dts2-<n> -b dts2/<stamp>/main-b<n> dts2/<stamp>/main` and works only inside it. `use_worktrees: never` is the explicit opt-out; `always` forces it in workspace mode too.
3. **One builder, one scratch dir (no git).** In a plain folder each builder owns `.harness/wt/<n>/` and a disjoint file list; the lead copies results into place and keeps a diff summary in the run folder.
4. **Lead merges, after green.** When the verifier reports VERIFIED, the lead merges each builder branch into `dts2/<stamp>/main` in plan order, re-runs the full test suite and every configured check after each merge, resolves conflicts itself, then removes the builder worktrees (`git worktree remove` + branch delete). A conflict it cannot resolve stops the run and goes to the user.
5. **Ship = receipt + user push.** At the ship checkpoint the lead commits on `dts2/<stamp>/main` with the receipt. As the last gate before `git commit`, the lead runs `npx skills add https://github.com/mattpocock/skills --skill setup-pre-commit` (`/setup-pre-commit`) so the repo's pre-commit hooks are in place, unless `companion-gate.py check` says the repo already had that pass. The user pushes; `gh pr create --body-file <receipt>` opens the PR; `pr-receipt.sh` guarantees the receipt section and template.
6. **PR checkout for review.** `run review-pr <number>` checks out the PR (`gh pr checkout <number>`), runs only the review and verify phases (walkthrough → reviewers → finish passes → verifier) on the PR diff against its base, and posts the findings as a PR comment on an explicit yes. It never builds or commits on a PR it did not open.
7. **Cleanup.** After the PR merges, `git worktree prune` and delete the local `dts2/<stamp>/*` branches; `.harness/runs/<stamp>/` stays as the record.

## Companion skills (installed per project, recorded in keep.yaml)

Installed with `npx skills add https://github.com/mattpocock/skills --skill <name>` (plus `-a claude-code --copy -y`, so Claude Code gets a real copy; a bare install's symlink silently fails on Windows) by the run Pre-check (`scripts/skills-check.py <repo> --fix`), which runs before every run command, installs any missing companion or keep.yaml skill. Its freshness sweep — removing retired skills, detecting one gone upstream, and writing update proposals for approval (never a bulk update) — is the network-heavy part, so it runs at most once a day (marker `.harness/.skills-checked`); the rest of the day the pre-check is a filesystem-only presence check that still installs anything missing. The per-moment install lines below remain as a fallback when the pre-check could not run. Each is recorded in `.harness/keep.yaml` so a setup re-run keeps them. Each is recorded as `- name: <name>` / `source: npx skills add https://github.com/mattpocock/skills --skill <name>` / `serves: harness` under `skills:`. Invoke an installed skill by its slash name with the Skill tool; when headless or the Skill tool is unavailable, read the installed skill's SKILL.md and follow it inline.

| skill | when the harness runs it |
|---|---|
| `grill-me` | setup: immediately after the deep interview, on the draft end state, before the first approval |
| `improve-codebase-architecture` | setup: immediately after the user's first sign-off of the end state (brownfield: against the code; greenfield: against the Blueprint and Sections). run: finalization pass before tests are written, after a builder's implementation is complete: ask `companion-gate.py check --skill improve-codebase-architecture` first and skip the pass on `run: false`; otherwise scope it to the builder's file set for a refactor plan on the just-written code (`npx skills add https://github.com/mattpocock/skills --skill improve-codebase-architecture`), apply the worthwhile simplifications inside the file set, then write the tests. If it cannot run, do a manual scoped simplification pass instead (duplication, dead code, unclear names, speculative abstraction). It replaces `request-refactor-plan`, which upstream retired into `to-spec` and `improve-codebase-architecture` |
| `writing-for-agents` | setup: after the amended end state is signed off again, to rewrite end-state.md and the lead's plan template into agent-friendly form |
| `pr` | run: every time a PR is created or its body is rewritten |
| `resolve-merge-conflicts` | run: whenever a merge conflict arises (builder branch merge, rebase, `review-pr`, `ship`, or `autopilot`). Source: `npx skills add warpdotdev/common-skills@resolve-merge-conflicts` (not mattpocock/skills: upstream removed `resolving-merge-conflicts`, so it is retired). Its SKILL.md names `.agents/skills/...` for its helper script; run `extract_conflict_context.py` from wherever the skill was installed (`.claude/skills/resolve-merge-conflicts/scripts/` with `--copy`) |
| `diagnosing-bugs` | run: at fix round 2 on the same failure, before the second fix; and again at the hard 5-round cap, bugs still failing, as a fresh `/diagnosing-bugs` pass (`npx skills add https://github.com/mattpocock/skills --skill diagnosing-bugs`) on everything still failing (upstream renamed `diagnose` to `diagnosing-bugs`, so the hard cap reruns that skill from scratch, not the round-2 output) before escalating to the user |
| `ask-matt` | setup/run: when the user asks a question (`/ask-matt`) |
| `research` | setup/run: when still unsure after ask-matt (`/research`) |
| `loop-me` | run: on /dt:run trigger — check in with the user, before dispatching builders (`npx skills add https://github.com/mattpocock/skills --skill loop-me`) |
| `setup-pre-commit` | run: once per repo, as the last gate before `git commit`, when `companion-gate.py check --skill setup-pre-commit` answers `run: true`; store it with `record` afterwards (`npx skills add https://github.com/mattpocock/skills --skill setup-pre-commit`) |
| `code-review` | setup/run: first contact — repo the harness has never been in (no `.harness/` marker); fires once per repo (`npx skills add https://github.com/mattpocock/skills --skill code-review`) |

A missing or failed install never blocks: print `Skill <name> not installed (npx unavailable or offline); continuing without it.`, add a Decisions action item with the command, continue.

## Composio routing (only when `~/.dts2/composio.json` has `always_use: true`)

1. **Cache first.** Check the cached tool map (`~/.dts2/composio-tools.json`) for the toolkit; search only when it is missing.
2. **One search per workflow.** Call `COMPOSIO_SEARCH_TOOLS` once with a session `generate_id` and reuse the returned `session_id` for every later meta call.
3. **Batch independent calls.** `COMPOSIO_MULTI_EXECUTE_TOOL` takes up to 50 independent calls; dependent calls run in sequence.
4. **Bulk work goes remote.** Use `COMPOSIO_REMOTE_WORKBENCH` or `COMPOSIO_REMOTE_BASH_TOOL` for large or file-based results (180 s per call; checkpoint to `/mnt/files/`).
5. **One connection.** Never run the Composio plugin and a hosted Composio MCP server at the same time.
6. **Memory is separate.** Memory stays with the knowledge store; Composio is a tools integration only. Credentials stay in the CLI's own config and never enter a repo, a chat or a log.
