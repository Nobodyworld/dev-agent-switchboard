# Prove reviewed-main fresh execution and exact reuse

This ExecPlan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as work proceeds. Maintain it in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Issue #146 and PR #147 discovered and corrected completion-boundary, compact-evidence, HTTP-diagnostic, and server-smoke fixture defects, but the original immutable target could not produce an authoritative successful fresh run or exact reuse. Issue #146 therefore closed as `not_planned / TARGET-STATE-BLOCKED` rather than being misrepresented as completed.

This successor slice proves the resulting reviewed `main` through one real fresh `validate-switchboard@1` run and one distinct same-worker `allow_exact` reuse. It adds no product architecture. Its observable result is a trustworthy server-accepted fresh run followed by cryptographically verified zero-step reuse, with exact evidence and complete cleanup.

The repository remains:

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

This slice does not authorize release, deployment, public hosting, external target execution, MCP, provider routing, expanded worker types, source-write authority, or production claims.

## Authority and Exact Starting State

```text
parent epic: #111
predecessor issue: #146 — closed not_planned / TARGET-STATE-BLOCKED
predecessor PR: #147 — squash-merged
active issue: #149
starting main and immutable acceptance target: e9b56ac0d5936e39d811b240a8091a54e1b4ff26
canonical branch: test/reviewed-main-fresh-reuse-acceptance
pull request: #150 — open draft
manifest: validate-switchboard@1
routing: first_available
fresh reuse_policy: never
reuse reuse_policy: allow_exact
approval: explicit for both requests
```

Issue #149 is the accepted contract. Do not reopen issue #146, substitute another target, or reuse any predecessor failed database or evidence as successful state.

## Observable Completion

An operator can start the reviewed merged server and one outbound worker, explicitly approve one fresh exact-SHA request, receive authoritative terminal success and accepted compact evidence, then approve a distinct equivalent `allow_exact` request and observe same-worker retained-evidence verification with zero repeated deterministic validation steps.

The final evidence must establish:

- exact repository, target SHA, manifest name/version/digest, worker, route, work-order, and run identities;
- all seven reviewed fresh steps executed and succeeded;
- server-accepted terminal success for the fresh run and work order;
- evidence fingerprint, reuse identity hash, artifact count/bytes/hashes, and retention expiry;
- a distinct reused run linked to the exact fresh source run;
- same-worker ownership and artifact verification;
- zero deterministic steps and no fresh fallback on reuse;
- unchanged source-evidence expiry;
- truthful avoided deterministic execution count;
- clean canonical source, lease, capacity, quota, process, port, worktree, and transient-path state.

## Progress

- [x] PR #147 squash-merged as `e9b56ac0d5936e39d811b240a8091a54e1b4ff26`.
- [x] Issue #146 closed with `not_planned / TARGET-STATE-BLOCKED` disposition.
- [x] Issue #149 created against exact reviewed `main`.
- [x] Canonical branch `test/reviewed-main-fresh-reuse-acceptance` created from exact target.
- [x] Living ExecPlan 017 created.
- [x] Draft PR #150 created and linked to issue #149.
- [ ] Synchronize a clean local canonical `main` to exact target `e9b56ac0...`.
- [ ] Create one clean local worktree for the canonical successor branch.
- [ ] Verify all three predecessor failed environments and `security-deferral-wip` remain preserved.
- [ ] Establish one brand-new short marker-owned runtime with isolated database, storage, worker, evidence, report, TEMP/TMP, tooling, and process-marker roots.
- [ ] Complete focused preflight validation of completion, evidence sanitization, HTTP diagnostics, routing, reuse, finalization, and server-smoke behavior.
- [ ] Start the reviewed server and one outbound worker with only the Switchboard repository mapping.
- [ ] Create, explicitly approve, queue, and execute one fresh exact-target `validate-switchboard@1` request.
- [ ] Prove seven-of-seven fresh steps, authoritative terminal success, accepted evidence, exact identity, and complete cleanup.
- [ ] Create, explicitly approve, queue, and complete one distinct equivalent `allow_exact` request on the same worker.
- [ ] Prove same-worker retained-evidence verification, exact source linkage, zero repeated deterministic steps, unchanged expiry, no fresh fallback, and truthful avoided-work count.
- [ ] Run the complete locally available validation matrix after successful fresh/reuse proof.
- [ ] Reconcile this ExecPlan and concise mutable status evidence without rewriting predecessor history.
- [ ] Commit only exact reviewed documentation/evidence-summary paths, push normally, and verify local/remote SHA parity.
- [ ] Complete exact-head hosted validation and connector review.
- [ ] Keep the PR draft and unmerged pending separate explicit owner authorization.

## Context and Orientation

Switchboard separates coordination from deterministic execution. Work orders bind one allowlisted repository, exact full SHA, immutable trusted manifest, explicit approval, routing policy, and reuse policy. The outbound worker creates a disposable exact-SHA worktree, executes fixed reviewed argv, retains full logs locally, returns bounded compact evidence, and may reuse evidence only after same-worker local cryptographic verification.

Relevant implementation and evidence areas include:

```text
server/execution/
server/api/routers/execution.py
client/python/execution_worker/
scripts/local_worker.py
web/static/validation_broker.js
docs/operations/local-worker.md
docs/reports/status.md
.agent/execplans/016_merged_workload_factory_acceptance.md
```

The predecessor failed environments are historical evidence. They must remain unchanged and must never be used as application state or reuse sources.

## Plan of Work

### 1. Preserve and synchronize local state

Begin read-only. Confirm repository identity, canonical and feature refs, worktree inventory, stash inventory, dirty files, and unpublished commits. Fast-forward canonical `main` only when it is clean and the target is exactly `e9b56ac0d5936e39d811b240a8091a54e1b4ff26`.

Create exactly one successor worktree from the prepared branch. Do not recreate deleted historical worktrees or perform broad cleanup. Preserve all predecessor evidence roots and `security-deferral-wip`.

### 2. Validate the reviewed acceptance boundary before execution

Run focused tests for:

- text/path and local SQLite URI policy;
- compact worker-summary sanitization;
- bounded typed HTTP diagnostics;
- completion schema and real FastAPI completion persistence;
- lease and capacity release;
- worker finalization and monitor behavior;
- server-backed worker smoke behavior;
- exact evidence reuse and artifact verification;
- routing and catalog identity.

If the reviewed target fails any mandatory focused or complete preflight gate, stop and report. Do not modify the immutable target or broaden the issue into implementation work.

### 3. Establish one brand-new isolated runtime

Use a short marker-owned root outside every repository and predecessor environment. Keep database, server storage, worker source, retained evidence, reports, TEMP/TMP, tooling, and process markers in distinct contained subroots.

Use one worker with one repository mapping:

```text
Nobodyworld/dev-agent-switchboard
    -> clean canonical checkout at exact e9b56ac0d5936e39d811b240a8091a54e1b4ff26
```

Use a new process-only test token. Do not persist or expose it in configuration, commands, logs, reports, evidence, commits, comments, or the final response.

### 4. Execute the authoritative fresh run

Create one new work order with exact target, `validate-switchboard@1`, `first_available`, `reuse_policy: never`, the reviewed timeout contract, and explicit approval.

Prove:

- request, work-order, run, worker, route, repository, SHA, manifest, and digest identity;
- seven reviewed steps selected, executed, and passed;
- completion returns success;
- run and work order persist as `succeeded`;
- compact result and evidence fingerprint persist;
- artifact count, bytes, hashes, and retention expiry persist;
- reuse identity/hash persists;
- canonical source tree and status are unchanged;
- disposable worktree, lease, capacity, quota, processes, ports, and transient source paths are clean;
- no prohibited local or secret material appears remotely.

If any mandatory step, completion, persistence, evidence, or cleanup check fails, preserve the new runtime and stop. Do not create a reuse request or manually repair database state.

### 5. Execute one exact reuse

Only after authoritative fresh success, create a distinct equivalent explicitly approved work order with `reuse_policy: allow_exact` on the same worker.

Prove:

- distinct work-order and run identities;
- exact fresh source-run selection;
- same-worker ownership marker verification;
- result identity and evidence-fingerprint verification;
- every retained artifact verifies containment, regular-file status, size, and SHA-256;
- source evidence remains within original retention;
- zero deterministic validation steps execute;
- no fresh fallback occurs;
- exact source-run linkage;
- unchanged source expiry;
- truthful avoided deterministic execution count;
- clean lease, capacity, quota, process, worktree, and transient-evidence state.

### 6. Validate and reconcile evidence

After fresh and reuse success, run the complete repository-local matrix. Update only concise living evidence and status surfaces needed to record the accepted proof. Do not modify production behavior unless a separate accepted issue authorizes it.

Stage only exact paths, use Conventional Commits, push normally, verify exact local/remote parity, and return to the GitHub connector for patch review and hosted validation.

## Concrete Steps

Resolve exact current commands from repository source and operations documentation. Read-only preflight should include equivalents of:

```powershell
git rev-parse --show-toplevel
git remote -v
git status --short --branch
git branch -vv
git worktree list --porcelain
git stash list
git fetch --prune origin
git rev-parse origin/main
git rev-parse origin/test/reviewed-main-fresh-reuse-acceptance
```

Expected immutable target:

```text
e9b56ac0d5936e39d811b240a8091a54e1b4ff26
```

Focused validation must cover the exact completion and reuse boundaries before live execution. Complete post-acceptance validation includes current equivalents of:

```text
python scripts/dev.py validate-workload-catalog
python scripts/dev.py verify
pre-commit run --all-files --show-diff-on-failure
python scripts/dev.py check-todos --root .
python -m ruff check .
python -m ruff format --check .
python -m black --check .
python -m mypy --config-file mypy.ini server client scripts
python -m pytest
SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py -rA
python -m bandit -q -r server -x server/tests
python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
gitleaks detect --verbose
git diff --check
```

Also run configured coverage thresholds, link checks when available, workflow/YAML/action-pin validation, Node syntax, secrets and public-path hygiene, and platform cleanup checks safely supported by the environment.

## Validation and Acceptance

The slice is accepted only when:

- fresh execution succeeds on exact reviewed target `e9b56ac0...`;
- all seven reviewed fresh steps pass;
- completion and evidence are accepted by the server;
- the reuse request is distinct and explicitly approved;
- same-worker local evidence and artifacts verify;
- zero deterministic validation steps repeat;
- source linkage, expiry, route, fingerprint, and avoided-work claims are exact;
- canonical source and every runtime/control-plane cleanup check pass;
- the complete local matrix passes or exact environment blockers are recorded;
- local/remote branch SHAs match after normal push;
- exact-head hosted workflows and connector review pass;
- the PR remains draft and unmerged pending owner authorization.

## Idempotence and Recovery

- Use unique work-order IDs and a new marker-owned runtime.
- Preserve all predecessor environments unchanged.
- Never manually repair or reinterpret a failed/running record.
- If fresh execution fails, preserve the new runtime and stop before reuse.
- If refs move or local state is dirty unexpectedly, stop before mutation.
- If cleanup ownership is uncertain, retain the resource and report it.
- Do not reset, clean, stash, rebase, amend, force-push, or broadly delete.

## Artifacts and Notes

Retain one compact sanitized campaign report outside the repository containing exact identities, bounded evidence, durations, artifact summaries, cleanup inventory, operator actions, validation summaries, and environment blockers. Do not commit or publish local paths, tokens, databases, full logs, virtual environments, browser caches, or raw environment dumps.

## Interfaces and Dependencies

Preserve the current reviewed interfaces for:

- `validate-switchboard@1`;
- exact-SHA work orders and explicit approval;
- `reuse_policy: never|allow_exact|require_exact`;
- outbound worker registration, heartbeat, polling, lease, completion, and evidence;
- compact evidence and retained local artifacts;
- same-worker exact evidence reuse;
- `first_available` routing;
- source-controlled workload catalog and manifest digests.

No new execution interface is authorized by this issue.

## Decision Log

- Decision: Close issue #146 as target-state blocked and create a successor against reviewed merged main.
  Rationale: The fixes required for authoritative completion existed only on PR #147; merging first created a clean immutable target and audit boundary.
  Date/Author: 2026-08-27 / Owner and GitHub coordinator.

- Decision: Keep the successor acceptance-only.
  Rationale: Architecture expansion would obscure whether the reviewed current product can complete fresh execution and exact reuse.
  Date/Author: 2026-08-27 / Owner and GitHub coordinator.

- Decision: Preserve all predecessor failed environments unchanged.
  Rationale: They are truthful historical evidence and must not be repaired, reused, or collapsed into the successor result.
  Date/Author: 2026-08-27 / Owner and GitHub coordinator.

## Surprises & Discoveries

Record new observations only as they occur. Do not copy predecessor failures as new evidence.

## Outcomes & Retrospective

Pending authoritative fresh and exact-reuse completion.