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
- [x] Open draft PR #147 linked to #146.
- [x] Safely fast-forward the canonical local `main` to the exact starting SHA.
- [x] Inventory local worktrees, local branches, stashes, unpublished commits, and dirty files.
- [x] Preserve `security-deferral-wip` and every uncertain user-owned resource.
- [x] Safely disposition every audited worktree and branch by retaining uncertain or squash-merge-attached resources; no worktree was removed.
- [x] Establish isolated acceptance server, database, worker root, evidence root, and exact repository mapping.
- [x] Execute a real fresh exact-SHA `validate-switchboard@1` attempt through every deterministic product component; all seven reviewed steps passed.
- [ ] Record an authoritative completed fresh run and clean control-plane lease/capacity state. Exact target `a21aa33...` is TARGET-STATE-BLOCKED after three preserved failed attempts.
- [ ] Execute one distinct equivalent `allow_exact` request. Not attempted because no authoritative successful source run exists; no fourth acceptance is authorized in this continuation.
- [ ] Prove same-worker retained-evidence verification and zero repeated deterministic steps. No reuse claim exists.
- [x] Record the measured fresh duration, retained evidence size, operator actions, retries, and friction; reuse measurements are not available.
- [x] Reconcile issue #111 body through the connector and update project status documentation.
- [x] Finalize ExecPlan 015 as completed historical evidence.
- [x] Add stable root `PROJECT_RULESET.md` with no moving status fields.
- [x] Reconcile README product quick start and historical release wording.
- [x] Remove the unsupported production monitor-cadence clamp and use the established five-second cadence only in the two self-throttling server-smoke fixtures.
- [x] Sanitize local SQLite DSNs recursively at compact worker-summary serialization while preserving strict raw server rejection.
- [x] Add bounded typed HTTP diagnostics and complete the schema/API completion-boundary regression.
- [x] Preserve all three failed acceptance environments and make no fourth live attempt.
- [x] Add a current-versus-historical banner to `PUBLIC_RELEASE_AUDIT.md`.
- [x] Update affected documentation indexes and operations guides.
- [x] Run focused acceptance tests and the complete locally available validation matrix; record bounded pip-audit and WSL dependency setup as environment-blocked.
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

- Decision: Classify exact target `a21aa33cabd143dbfefebe4ba32572ddb5765752` as TARGET-STATE-BLOCKED and do not run a fourth acceptance in this correction session.
  Rationale: Its two server-smoke tests configure `0.05`-second heartbeats and can self-exhaust the default `120` requests per `60` seconds limiter after preceding combined-suite workload. The immutable target cannot receive the test-only correction.
  Date/Author: 2026-08-27 / Owner and correction campaign.

- Decision: Restore production monitor cadence to the remote-head behavior and correct only the two server-smoke test configurations to five seconds.
  Rationale: Isolated tests pass and no independent production contract justifies a global two-second minimum solely for suite stability.
  Date/Author: 2026-08-27 / Owner and correction campaign.

## Surprises & Discoveries

- Observation: The documented direct-file worker launcher fails from a source
  checkout before registration because Python does not place the repository root
  on the import path.
  Evidence: `python scripts/local_worker.py` raised `ModuleNotFoundError` for a
  repository package; `python -m scripts.local_worker` is the working interface
  and is now documented.

- Observation: A shared machine Python environment is not valid evidence for
  this profile, and the fixed nested acceptance tests need the reviewed Node and
  pnpm capabilities even though `validate-switchboard@1` itself declares only
  Python.
  Evidence: The shared environment reported unrelated pip conflicts and an
  older Ruff. A campaign-scoped Python 3.14 environment with exact development
  requirements, Node 24.19.0, and pnpm 10.18.1 produced the successful seven-step
  execution.

- Observation: The final successful deterministic execution could not be
  committed to the control plane because a relative Windows path became
  UNC-shaped only after JSON string serialization.
  Evidence: Work order `1` / run `1` completed seven steps and finalized local
  evidence, then `POST /api/execution/runs/1/complete` returned HTTP 422. The
  retained summary contains a relative `..\..` package path; JSON escaping
  produces doubled backslashes that the server correctly rejects. A focused
  regression reproduces the policy failure, and final summary serialization now
  replaces literal backslashes with `[BACKSLASH]`.

- Observation: The second isolated attempt failed five exact-target tests only
  under combined-suite load.
  Evidence: Three Windows cancellation cases exceeded their end-to-end
  four-second expectation, and the two server-backed smoke cases returned HTTP
  `429` with `0.05`-second heartbeats. The same five exact nodes, all three
  cancellation nodes under Windows Job Object containment, and the complete
  server-smoke module passed in isolated exact-target reproduction.

- Observation: The third isolated attempt proved the backslash correction but
  exposed a separate compact-evidence boundary.
  Evidence: Five deterministic steps passed; the target test step reported
  `696` passed, `12` skipped, and the same two self-throttling server-smoke
  failures. Completion returned bounded HTTP `422` because retained source text
  contained `sqlite+aiosqlite:///` shaped local database syntax. The database,
  evidence, lease, and capacity state remain unchanged, and no reuse request was
  created.

- Observation: The required 2026-08-25 external-target re-resolution found
  Industry Resilience PR #130 closed and merged at reviewed head
  `e3fea89db624414fe3cad7980768f0265cf9570a` and merge commit
  `f99abbf42c898f0fe4a7494f09b4aae13bed5c40`.
  Evidence: Current GitHub PR metadata plus successful exact-head Quality Gate
  run `32536731040` and Docker Smoke run `32536731320`. Exact-PR dogfood is now
  TARGET-STATE-BLOCKED. Zscripts PR #119 remains closed/merged and
  TARGET-STATE-BLOCKED at current reviewed main `c96628e...`.

## Outcomes & Retrospective

The campaign proved that merged `validate-switchboard@1` can traverse the real
server, explicit approval, first-available routing, outbound worker, exact-SHA
worktree, fixed runner, evidence finalization, canonical integrity, and source
cleanup path. On exact `a21aa33cabd143dbfefebe4ba32572ddb5765752`, all seven
steps succeeded in `801.538211` seconds. Pytest reported `700` passed, `10`
skipped, no failures/errors, and `94%` measured server coverage. Fourteen
retained artifacts totaled `16,980` bytes; fingerprint
`b5509a847335785930b6d89536d9b31bfcb4f21bb71f0d08afbceb1cfc2e2957`
and reuse identity hash
`fdcbf853a6f045a5136ad812b6720fcd10e194ab09a6abfb382137de80a3a3dc`
were finalized locally. The canonical source remained clean and unchanged, the
disposable worktree was removed, and worker/server processes were stopped.

The final issue #146 acceptance disposition is TARGET-STATE-BLOCKED. Three
isolated failed attempts are preserved without database repair or evidence
deletion. The first ran all seven steps but failed completion on serialized
Windows backslashes. The second failed three combined-load cancellation timing
expectations and two self-throttling server-smoke tests. The third passed five
steps, failed those same two server-smoke tests with HTTP `429`, did not run the
required security step, and then failed completion on local SQLite DSN-shaped
source text. There is no authoritative successful source run, distinct reuse
request/run, same-worker retained-evidence verification, zero-step reuse proof,
or avoided-work duration/count. No fourth acceptance ran.

The correction restores production monitor cadence to the caller-configured
remote-head behavior and changes only the affected server-smoke fixtures from
`0.05` to five seconds. The worker recursively replaces complete local SQLite
DSNs with `[LOCAL_DATABASE_URI]` before compact summary submission; full local
logs remain governed by their existing ownership and retention policy. The
server still recursively rejects raw Windows/POSIX absolute paths, `file:` URIs,
and SQLite DSNs. Typed HTTP errors retain only status, stable reason, and at most
eight sanitized validation entries with bounded location, type, and message;
raw response text, request bodies, validation `input`, arbitrary context,
credentials, HTML, local paths, and local DSNs are not retained.

Correction validation passed the schema/text-policy/finalization/client/monitor
selection (`86` tests), the two formerly failing server-smoke cases individually
and together, and three consecutive complete server-smoke module runs (`8`
tests each) without HTTP `429`. The exact candidate manifest pytest command
passed `735` tests with `10` documented platform skips and `94%` aggregate
`server` coverage. The independent plain full suite matched at `735` passed and
`10` skipped. Every configured module threshold passed from `87.76%` through
`100%`; strict Playwright passed four cases with zero skips. Repository-pinned
Ruff `0.16.2` and Bandit `1.9.4`, Mypy, scoped pre-commit, Gitleaks across `296`
commits, detect-secrets, TOML/YAML, Node syntax, full-SHA action pins, catalog,
TODO, formatting, diff, and public-path checks passed.

Three local validation limitations remain explicit. The `verify` orchestrator
could not launch `bandit` because the shared Python installation lacks a
`bandit.exe`; its Ruff, Mypy, coverage, and module gates ran independently, and
the pinned Bandit module passed through `uvx`. The environment safety boundary
rejected all-files pre-commit because hooks can rewrite unrelated paths; the
same configured hooks passed on every explicitly changed path. Lychee is not
installed, so documentation-link validation is environment-blocked. The single
bounded `pip-audit` run completed against the contaminated shared Python
environment and reported `117` advisories across `29` packages plus eight
unavailable local packages; it is not project dependency evidence or a pass.

Two additional developer-gate defects were corrected without weakening policy:
`scripts/dev.py verify` now excludes `server/tests` from Bandit exactly like the
trusted manifest and protected workflow, and it now includes
`server.observability.overview` in coverage because that same command enforces
an overview threshold. A focused CLI regression binds both argv contracts.

Operator friction was dominated by multi-process setup, configuration of one
exact canonical mapping, manual API creation and approval, capability matching,
long nested-suite feedback, a default pytest temp-owner permission failure, and
the difference between isolated test behavior and combined-suite rate limiting.
The three live acceptance environments remain preserved. A separate
task-specific correction-validation temp root was used only for local pytest;
it was not a server/worker acceptance environment and created no work order.
The future supported operator command should compose server/worker lifecycle,
preflight tool capabilities, request creation/approval observation, and bounded
cleanup reporting. It must not infer repository authority, approval, tokens, or
isolation trust decisions.

All seven registered worktrees were clean and had no staged, unstaged, or
untracked content. The primary remained on exact `main`; the campaign worktree
remains required for PR #147. Merged feature worktrees were retained because
their squash-merged branch tips are not ordinary ancestors of `main`, and the
campaign does not authorize force deletion. The public-workload worktree was
also retained because its local tip differs from the final reviewed PR #145
head; the pull-worker branch/worktree was retained because its local tip differs
from reviewed PR #119 head. The closed-unmerged security branch and
`security-deferral-wip` stash were preserved. No worktree or uncertain branch
was deleted. The unattached `codex/harden-public-release-readiness` branch was
the sole normal deletion: its tip exactly matched PR #88's reviewed merge
commit, and `git branch -d` succeeded without force.
