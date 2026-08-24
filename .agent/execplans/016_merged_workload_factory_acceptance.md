# Prove the merged workload factory and reconcile project truth

This ExecPlan is a living document. Keep `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` current as work proceeds. Maintain it in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Issue #143 and PR #145 merged the repeatable source-controlled workload factory into Switchboard. The merged code has strong synthetic production-path coverage and exact-head hosted validation, but the project still needs one real operator-controlled run against the merged product itself. Several durable records also still describe the completed #143 campaign as active.

This slice proves that current `main` can execute one fresh exact-SHA `validate-switchboard@1` run and one exact retained-evidence reuse through the real FastAPI server, outbound worker, routing, leases, worktrees, evidence store, and Validation Broker. It then reconciles GitHub and repository documentation so future agents do not restart completed work or mistake historical release evidence for current status.

The repository remains:

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

This slice does not authorize production, public hosting, external target execution, MCP, paid-provider routing, expanded worker types, write-capable automation, release, or deployment.

## Authority and Exact Starting State

```text
parent epic: #111
issue: #146
starting main: a21aa33cabd143dbfefebe4ba32572ddb5765752
canonical branch: test/merged-workload-factory-acceptance
pull request: created through the GitHub connector after this plan commit
```

Issue #146 is the accepted contract. The current branch must remain one coherent acceptance-and-reconciliation campaign. Do not reopen or reimplement issue #143.

## Observable Completion

An operator can point the real merged system at exact current `main`, explicitly approve a fresh validation, receive bounded trustworthy evidence, request a distinct equivalent `allow_exact` validation, and observe same-worker reuse with zero repeated deterministic steps.

The final public/project authority must state the same current truth:

- #143 is completed;
- PR #145 is merged;
- current `main` is `a21aa33cabd143dbfefebe4ba32572ddb5765752` at slice start;
- #146 is the active acceptance slice;
- the developer-preview tag is a historical checkpoint, not current-main release coverage;
- the next architectural expansion remains unstarted.

## Progress

- [x] PR #145 squash-merged at `a21aa33cabd143dbfefebe4ba32572ddb5765752`.
- [x] Issue #143 closed as completed.
- [x] Issue #146 created with the accepted scope and exclusions.
- [x] Canonical branch `test/merged-workload-factory-acceptance` created from exact starting `main`.
- [x] Living ExecPlan 016 created.
- [ ] Open one draft PR linked to #146.
- [ ] Safely fast-forward the canonical local `main` to the exact starting SHA.
- [ ] Inventory local worktrees, local branches, stashes, unpublished commits, and dirty files.
- [ ] Preserve `security-deferral-wip` and every uncertain user-owned resource.
- [ ] Remove only clean, proven-merged campaign worktrees and local branch names.
- [ ] Establish isolated acceptance server, database, worker root, evidence root, and exact repository mapping.
- [ ] Execute one fresh exact-SHA `validate-switchboard@1` request through the real product path.
- [ ] Verify exact identity, route, worktree, evidence, source integrity, cleanup, and no leaks.
- [ ] Execute one distinct equivalent `allow_exact` request.
- [ ] Prove same-worker retained-evidence verification and zero repeated deterministic steps.
- [ ] Record fresh/reuse durations, retained evidence size, operator actions, and friction.
- [ ] Reconcile issue #111 body and project status documentation.
- [ ] Finalize ExecPlan 015 as completed historical evidence.
- [ ] Add stable root `PROJECT_RULESET.md` with no moving status fields.
- [ ] Reconcile README product quick start and historical release wording.
- [ ] Add a current-versus-historical banner to `PUBLIC_RELEASE_AUDIT.md`.
- [ ] Update affected documentation indexes and operations guides.
- [ ] Run focused acceptance tests and the complete local validation matrix.
- [ ] Commit logical Conventional Commit units using exact-path staging.
- [ ] Push normally and verify local/remote SHA parity.
- [ ] Complete exact-head hosted validation and connector review.
- [ ] Keep the PR draft and unmerged until separate owner authorization.

## Context and Orientation

Switchboard separates high-level task coordination from trusted deterministic execution. Work orders identify one allowlisted repository, one exact full SHA, one immutable trusted manifest, and an explicit approval lifecycle. Outbound workers poll for work, create disposable exact-SHA worktrees, execute fixed reviewed argv, retain full logs locally, return compact evidence, and may reuse evidence only after same-worker local cryptographic proof.

Relevant implementation areas include:

```text
server/execution/
server/api/routers/execution.py
client/python/execution_worker/
scripts/local_worker.py
web/static/validation_broker.js
web/tests/test_ui.py
docs/operations/local-worker.md
docs/operations/validation-command-center.md
docs/reports/status.md
```

The accepted source profile is:

```text
repository: Nobodyworld/dev-agent-switchboard
commit: a21aa33cabd143dbfefebe4ba32572ddb5765752
manifest: validate-switchboard@1
```

The exact source commit must already exist in the operator-approved canonical local repository. The worker must not fetch, substitute another SHA, modify the canonical checkout, or publish to GitHub.

## Plan of Work

### 1. Preserve and synchronize local state

Begin read-only. Confirm repository identity, branch, current local and remote refs, worktree inventory, stash inventory, and status. Fast-forward the canonical local `main` only when it is clean and the update is exact.

The owner has multiple local branches whose remote branches were removed after squash merges, and several are attached to worktrees. A branch being `gone` does not by itself authorize deletion. For each candidate:

1. inspect worktree status;
2. inspect unpublished commits relative to all refs;
3. confirm the corresponding PR merged or the work is otherwise superseded;
4. preserve unique files or evidence;
5. remove the worktree only when clean and proven disposable;
6. delete the local branch name only after worktree removal and explicit verification.

Never use broad `git clean`, `git reset`, automatic stashing, or force operations.

### 2. Establish one isolated real acceptance environment

Use isolated campaign-owned paths outside the canonical source checkout for:

- server database;
- worker root;
- evidence root;
- reports;
- virtual environments or managed runtimes;
- browser assets when required.

Use one worker with only the logical repository mapping for `Nobodyworld/dev-agent-switchboard`. Keep worker and evidence roots distinct from each other and from every canonical checkout.

Use an operator-provisioned test admin token in the environment only. Do not place it in files, commands, logs, evidence summaries, screenshots, commits, or GitHub comments.

### 3. Execute one fresh run

Start the real FastAPI server and outbound worker. Submit an exact-SHA work order for `validate-switchboard@1` with `reuse_policy: never`, explicitly approve it, and allow the real worker to claim it.

Capture bounded evidence proving:

- exact repository and SHA;
- manifest name, version, and digest;
- approval and route identity;
- selected worker;
- fresh execution decision;
- complete fixed-step inventory;
- bounded parsed result;
- retained artifact hashes and expiry;
- canonical source integrity;
- source worktree cleanup;
- terminal state and lease cleanup;
- capacity and quota lifecycle;
- no local path or secret in remote evidence.

### 4. Execute one exact reuse

Create a distinct equivalent work order with `reuse_policy: allow_exact`. It must not reuse the same work-order identity. Explicitly approve it and route it to the same worker.

Prove:

- exact identity match;
- source-run candidate linkage;
- same-worker ownership marker verification;
- retained result and artifact hash verification;
- non-expired evidence;
- zero repeated validation steps;
- new auditable run identity;
- truthful avoided deterministic execution count;
- unchanged source evidence expiry;
- no fallback fresh execution;
- no leaked lease, worktree, process, capacity, quota, or transient evidence.

### 5. Reconcile durable truth

Update current mutable authority:

- issue #111 body;
- `docs/reports/status.md`;
- README current quick start and release wording;
- operations docs affected by observed friction;
- documentation index links.

Finalize historical authority:

- mark ExecPlan 015 complete;
- add final merge and outcomes retrospective;
- preserve detailed #143 evidence without presenting it as active work;
- add a historical-candidate banner to `PUBLIC_RELEASE_AUDIT.md`.

Add `PROJECT_RULESET.md` from the owner-provided draft, normalized to stable rules. The stable ruleset must not contain current branch, current SHA, active PR, test count, workflow ID, or dated status snapshot. It should point readers to `docs/reports/status.md`, GitHub issues/PRs, and living ExecPlans for changing facts.

### 6. Validate, publish, and return to connector review

Run focused acceptance selectors first, then the complete local matrix. Inspect all hook-made changes. Commit only explicit paths with Conventional Commit subjects. Push normally to the existing branch and verify exact local/remote parity.

Return to the GitHub connector for complete patch review, hosted workflow inspection, comments/reviews/thread reconciliation, and owner-decision support.

## Concrete Steps

Resolve exact current commands from source rather than treating this plan as a substitute for inspection.

Read-only preflight should include equivalents of:

```powershell
git rev-parse --show-toplevel
git remote -v
git status --short --branch
git branch -vv
git worktree list --porcelain
git stash list
git log --oneline --decorate --graph --all -n 50
git fetch --prune origin
git rev-parse origin/main
```

Expected starting remote `main`:

```text
a21aa33cabd143dbfefebe4ba32572ddb5765752
```

Required repository validation includes the current equivalents of:

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

Also run:

- the focused fresh/reuse acceptance selector;
- aggregate and every configured module coverage threshold;
- workflow YAML and action-pin validation;
- documentation links;
- public path and credential hygiene;
- accidental binary/generated-file checks;
- Windows and Linux/WSL process/cleanup checks where safely available.

## Validation and Acceptance

The slice is accepted only when:

- the fresh run executes on exact `a21aa33...` through production components;
- the reuse run is a distinct approved request;
- reused evidence is verified locally on the same worker;
- zero validation steps repeat during reuse;
- evidence identity and artifact hashes are exact;
- canonical source remains unchanged;
- all temporary source, process, lease, capacity, quota, and route state is clean;
- remote evidence contains no secret or absolute local path;
- the full local matrix passes or exact environment blockers are recorded;
- documentation and GitHub authority describe the current state consistently;
- local cleanup loses no user work or stash;
- the worktree is clean and local/remote branch SHAs match;
- hosted checks pass on the exact final head;
- connector review finds no unresolved blocker;
- the PR remains draft and unmerged pending owner authorization.

## Idempotence and Recovery

- The acceptance environment must be marker-owned and safely removable.
- Repeating the fresh/reuse proof with new work-order IDs must not corrupt prior evidence.
- Database startup and shutdown must remain repeatable.
- Do not reuse an uncertain evidence directory from an earlier campaign.
- If local `main`, the canonical branch, or remote refs move unexpectedly, stop and report exact state.
- If a worktree contains unknown changes or unpublished commits, retain it.
- If cleanup ownership is uncertain, retain the resource and report it.
- If the worker or server loses authority, stop execution and report the bounded terminal reason.
- Do not repair shared Git object permissions or global toolchains merely to complete this slice.

## Artifacts and Notes

Retain one compact sanitized local evidence directory outside the repository containing:

- exact environment and ref inventory;
- fresh and reuse request/run identities;
- commands and exit codes;
- bounded evidence JSON;
- test and coverage summaries;
- cleanup inventory;
- operator action count and friction notes;
- scanner summaries;
- local branch/worktree cleanup disposition.

Do not commit or publish local paths, credentials, environment dumps, full logs, generated databases, virtual environments, external source copies, browser caches, or unbounded reports.

## Interfaces and Dependencies

Preserve the current stable interfaces for:

- `validate-switchboard@1`;
- exact-SHA work orders;
- explicit approval;
- `reuse_policy: never|allow_exact|require_exact`;
- outbound worker registration, heartbeat, polling, lease, completion, and evidence;
- source-controlled workload catalog and manifest digests;
- route and readiness projections;
- Validation Broker fresh/reuse presentation;
- compact evidence and retained local artifacts.

This slice should not add a new execution interface unless a genuine acceptance defect requires a narrow fix with regression coverage.

## Decision Log

- Decision: Run acceptance against Switchboard itself rather than an external target.
  Rationale: It proves current product utility without introducing the unresolved hostile-public-target isolation boundary.
  Date/Author: 2026-08-24 / Owner and GitHub coordinator.

- Decision: Reconcile project truth in the same slice as real acceptance.
  Rationale: The observed documentation drift is an operational defect that directly affects future agent execution and handoffs.
  Date/Author: 2026-08-24 / Owner and GitHub coordinator.

- Decision: Keep MCP, provider routing, and specialized workers excluded.
  Rationale: Transport and architecture expansion should follow proof of current local-first utility and observed operator friction.
  Date/Author: 2026-08-24 / Owner and GitHub coordinator.

- Decision: Normalize the Project ruleset into a stable repository file without moving status.
  Rationale: Stable governance and mutable status need separate authoritative homes to prevent repeated drift.
  Date/Author: 2026-08-24 / Owner and GitHub coordinator.

## Surprises & Discoveries

Record findings here during local work.

## Outcomes & Retrospective

Complete this section after the final exact-head connector review. Record what the real run proved, where the operator flow was cumbersome, what local cleanup occurred, and what should be the next separately authorized slice.
