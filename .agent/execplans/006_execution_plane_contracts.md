# Add execution-plane contracts and lifecycle APIs

This ExecPlan is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be
maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Switchboard already coordinates high-level agent tasks but cannot safely
request deterministic local validation. The first implementation stage adds a
separate execution-plane domain:

- approved work orders;
- worker capability registration;
- immutable command-manifest identities;
- execution-run lifecycle records.

After this stage, an operator can create and approve a read-only work order for
an allowlisted repository and exact Git SHA. One eligible worker can atomically
check out the work and create an active execution run.

No command is executed in this stage. The observable outcome is a typed,
persisted control-plane lifecycle that the local worker in issue #113 can
safely consume.

Primary implementation issue: #112. Parent product epic: #111.

## Progress

- [x] Product direction and Phase 1 boundaries settled.
- [x] Architecture documented in
      `docs/architecture/local-execution-broker.md`.
- [x] Phase 1 backlog split into issues #112, #113, and #114.
- [x] Reconfirm the current `origin/main` SHA before implementation.
- [x] Inspect router, repository, migration, authentication, and test patterns.
- [x] Add execution-plane enums, schemas, models, and repositories.
- [x] Add validated lifecycle and capability-matching services.
- [x] Add `/api/execution/...` routes with appropriate authorization.
- [x] Add additive startup compatibility behavior without a migration framework.
- [x] Add unit, API, concurrency, persistence, and authorization tests.
- [x] Update API and message-schema documentation.
- [ ] Run complete repository validation.
- [ ] Open a draft PR linked to #112 and update this plan with evidence.

## Surprises & Discoveries

- Observation: `scripts/local_runner.py` is a coordination demonstration only.
  It checks out a task, maintains a heartbeat, or marks a task complete. It does
  not execute work.

  Evidence: The file contains no process, worktree, manifest, artifact, or
  environment-management implementation.

- Observation: Existing task records do not contain the execution identity or
  security policy required for local validation.

  Evidence: `TaskIn`, `TaskOut`, and the `Task` SQLAlchemy model contain task
  description, dependency, priority, status, and completion information only.

- Observation: `main`, `origin/main`, and
  `origin/feat/execution-plane-contracts` all resolved to
  `1dbd939854ab287430d1d9c24865e7ad51cbc29c` before edits, and the worktree was
  clean.

  Evidence: `git fetch origin --prune`, `git switch
  feat/execution-plane-contracts`, `git pull --ff-only`, `git rev-parse HEAD
  origin/main origin/feat/execution-plane-contracts`, and `git status --short`
  completed on 2026-07-12.

- Observation: The existing execution YAML is deliberately a non-executable
  later-stage contract example, not a request-driven manifest registry.

  Evidence: `docs/examples/execution/validate-switchboard-v1.yaml` says it is
  not executable until issues #112--#114. Phase 1A will therefore seed only
  version-controlled identity and safe contract metadata; no API accepts
  commands, argv arrays, script text, or executable paths.

- Observation: SQLite does not give a reliable row-locking guarantee through
  `with_for_update()` for this use case.

  Evidence: Existing task checkout uses a conditional affected-row update.
  Execution checkout will pair guarded status and capacity updates with a
  unique active-lease row and test the behavior against a file-backed SQLite
  database using independent sessions.

- Observation: The sandbox denies pytest's default user-temp directory and
  `C:\tmp`, but accepts a repository-local `--basetemp` directory.

  Evidence: The initial focused test run failed at fixture setup with
  `PermissionError` creating `%LOCALAPPDATA%\Temp\pytest-of-Nobod`; a rerun
  with `--basetemp .pytest-tmp-112c` ran all execution tests successfully.

- Observation: SQLAlchemy string-enum defaults use member names unless a
  `values_callable` is supplied; SQL expressions in guarded worker updates then
  need the same representation as row deserialization.

  Evidence: The first focused execution test pass surfaced a lookup error for
  stored `busy` / `online` values. Execution enums now explicitly persist their
  lower-case API values, and the focused suite passes.

- Observation: The installed Black process reformatted several files but did
  not finish within 120 seconds when given the full changed path set.

  Evidence: `black ...` timed out after reporting five reformatted files.
  `ruff format` completed formatting the remaining changed files; final Black
  validation remains pending.

- Observation: Top-level strict Pydantic fields alone do not prevent a caller
  from hiding executable-shaped keys inside JSON metadata.

  Evidence: Review found nested `manifest.parameters.argv` and metadata
  dictionaries were accepted before validation. The request models now
  recursively reject command, argv, shell, script, and executable keys in all
  caller-controlled mapping/list metadata.

- Observation: A stale-lease reader must not be allowed to terminalize a run
  after a concurrent heartbeat renewed the lease.

  Evidence: Execution lease mutation now uses conditional SQL updates/deletes
  and affected-row checks. Independent file-backed SQLite tests exercise both
  heartbeat-versus-expiry and completion-versus-cancellation races.

- Observation: A persisted manifest digest is insufficient as the sole trust
  check because other persisted fields could be modified without changing it.

  Evidence: Registry synchronization now compares every persisted manifest
  field against the version-controlled definition and rejects a mismatch; a
  metadata-tampering regression test covers the behavior.

- Observation: Substantial repository work must use a self-contained living
  ExecPlan.

  Evidence: `.agent/PLANS.md`.

Add implementation discoveries here as they occur. Preserve failed approaches
and unexpected constraints that affect future work.

## Decision Log

- Decision: Keep task coordination separate from the new execution-plane
  domain.

  Rationale: Dependency scheduling and deterministic command execution have
  different lifecycle, security, evidence, retry, and lease semantics. Reusing
  task leases would create ambiguous ownership and unreliable evidence.

  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Implement a pull-based worker with no inbound workstation listener.

  Rationale: Outbound polling is easier to secure, works behind common
  firewalls, and supports future GitHub or MCP adapters without exposing the
  local machine.

  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Permit only immutable trusted manifest identities in Phase 1A;
  reserve direct argument-vector execution for #113.

  Rationale: Arbitrary command strings would turn Switchboard into a remote
  shell and make approval meaningless. Issue #112 therefore stores only safe
  server-controlled manifest metadata and does not expose argv or launch a
  process.

  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Keep target repositories read-only in Phase 1.

  Rationale: The first objective is eliminating paid-agent validation work.
  Autonomous source changes and Git writes require a separate trust model.

  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Implement execution concerns in a focused `server/execution/`
  package, with SQLAlchemy models remaining in `server/models.py` so startup
  `Base.metadata.create_all()` discovers the new additive tables.

  Rationale: This preserves the existing task DAG, task checkout, task agents,
  and task leases while following the repository's central ORM convention.

  Date/Author: 2026-07-12 / Codex

- Decision: Treat a unique `execution_leases.work_order_id` row as the active
  run invariant and reserve worker capacity with a guarded SQL update.

  Rationale: The lease row can be deleted on terminal completion or stale
  expiry while the immutable execution-run history remains. Conditional
  updates and affected-row checks remain safe across independent SQLite
  sessions.

  Date/Author: 2026-07-12 / Codex

- Decision: Reuse the configured admin token for all execution endpoints in
  Phase 1, including worker registration and run operations.

  Rationale: It meets the accepted temporary credential boundary without
  adding an identity system. Documentation will explicitly mark this as a
  Phase 1 limitation for issue #113 to replace.

  Date/Author: 2026-07-12 / Codex

- Decision: Keep the trusted registry metadata-only in Phase 1A and calculate
  its SHA-256 digest from a canonical representation of that reviewed data.

  Rationale: The contract can be persisted and audited without turning the
  Phase 1A API into a source of executable argv data. Later worker execution
  needs its own reviewed trust boundary.

  Date/Author: 2026-07-12 / Codex

- Decision: Approval queues a work order by default but supports an explicit
  `approved` intermediate state when the caller sends `{"queue": false}`.

  Rationale: This makes the normal safe path ergonomic while keeping every
  required lifecycle state observable and transition-validated.

  Date/Author: 2026-07-12 / Codex

- Decision: Persist only bounded artifact/evidence metadata placeholders in
  Phase 1A; defer artifact collection, storage, retention, and redaction to
  #114.

  Rationale: #112 must not execute commands or collect artifacts. The
  placeholders preserve a typed future interface without claiming a worker or
  artifact-storage implementation exists.

  Date/Author: 2026-07-12 / Codex

- Decision: Make the active execution lease the exclusive lifecycle gate for
  heartbeat, terminal completion, cancellation, and stale expiry.

  Rationale: Conditional lease renewal and exact guarded lease consumption
  prevent a stale expiry from overriding a renewed heartbeat and ensure only
  one actor can terminalize a run and release worker capacity.

  Date/Author: 2026-07-12 / Codex

## Outcomes & Retrospective

Issue #112 adds a fully separate persisted control plane: command-manifest
snapshots, work orders, workers, execution runs, and unique active execution
leases. The legacy task DAG, task checkout, task leases, task agents, and task
completion behavior remain untouched; a focused regression checks a normal
legacy task checkout/lease alongside execution checkout.

Startup remains additive through `Base.metadata.create_all()` for both fresh
and pre-existing core-table databases; no Alembic or migration-framework work
was introduced. The static trusted registry supplies immutable manifest
identity and digest, validates every persisted snapshot field, and accepts no
request-controlled executable data. Request models recursively reject nested
command, argv, shell, script, and executable keys.

Checkout combines guarded worker capacity reservation, guarded queued-order
claim, and unique active lease creation. Heartbeat renewals and all terminal or
stale-expiry actions use guarded lease DML so one lease consumer alone may
update lifecycle records and release capacity. Expiry preserves run history,
marks the old attempt `timed_out`, and requeues the work order for an incremented
attempt. Independent file-backed SQLite tests cover concurrent checkout,
heartbeat-versus-expiry, and completion-versus-cancellation outcomes.

All execution endpoints reuse `SWITCHBOARD_ADMIN_TOKEN` when configured. That
includes worker registration, checkout, heartbeat, and completion and is a
documented temporary Phase 1 limitation, not a worker identity solution.

No issue-#112 code executes a command, creates a worktree, writes a target
repository, collects artifacts, or performs GitHub access. Safe pull-worker
execution remains #113; artifact/evidence collection, retention, and compact
evidence APIs remain #114. Final validation, commit SHA, push, and draft-PR
evidence are recorded below after delivery.

## Validation Record (2026-07-12)

Tool versions: Python 3.14.0; Ruff 0.14.2; Black 26.5.1; mypy 1.18.2;
pip-audit 2.7.3. The last focused execution run used independent file-backed
SQLite sessions and passed `23` tests in 10.36s, including checkout,
heartbeat-versus-expiry, completion-versus-cancellation, startup, API, and
legacy-task-lease coexistence coverage.

Final repository commands and results:

- `python -m pre_commit run --all-files --show-diff-on-failure` — exit 0; all
  configured hooks passed (Prettier skipped because it had no matching files).
- `ruff check server client scripts tests web switchboard_cli.py
  switchboard_client.py` — exit 0.
- `black --check server client scripts tests web switchboard_cli.py
  switchboard_client.py` — exit 0.
- `mypy --config-file mypy.ini server client scripts` — exit 0; 133 source
  files with no issues.
- `pytest -q` — exit 0; 252 passed, 2 skipped, 350 known legacy/runtime
  warnings in 85.85s.
- `SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py -rA`
  — exit 0; 2 passed.
- Bundled Python 3.12 with pinned `bandit==1.8.6`: `python -m bandit -q -r
  server -x server/tests` — exit 0. The installed Python 3.14 cannot run that
  Bandit release correctly (`Constant.s` compatibility failure), so the
  isolated scan was used and its temporary virtual environment was removed.
- `python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt`
  — exit 0; no known vulnerabilities.
- `gitleaks detect --verbose` — exit 0; 163 commits / 2.74 MB scanned with no
  leaks.
- `git diff --check` — exit 0; only pre-existing CRLF normalization warnings.

`python -m pip check` exits 1 in the shared Python 3.14 installation because
the unrelated global `opencv-python 4.12.0.88` package requires
`numpy <2.3.0` while that installation contains `numpy 2.3.4`; it also reports
an invalid global `~andit` distribution. No project dependency was changed. An
earlier isolated Python 3.12 virtual environment installed from
`server/requirements-dev.txt` and returned `No broken requirements found`; the
temporary environment was removed after validation.

## Context and Orientation

Relevant existing files:

- `server/models.py` defines SQLAlchemy persistence models.
- `server/schema.py` contains shared Pydantic API contracts.
- `server/application/task_service.py` contains task and lease lifecycle logic.
- `server/infrastructure/repositories.py` provides persistence adapters.
- `server/api/routers/` contains focused API routers.
- `server/api/lifecycle.py` handles startup and compatibility work.
- `server/settings.py` contains validated runtime configuration.
- `server/tests/` contains API, service, security, and concurrency patterns.
- `docs/API.md` documents routes.
- `docs/message-schema.md` documents serialized contracts.
- `docs/architecture/local-execution-broker.md` defines accepted boundaries.
- `docs/examples/execution/validate-switchboard-v1.yaml` is a later-stage
  contract example and is not executable during issue #112.

The current task DAG remains authoritative for coordination. Execution records
are additive.

## Plan of Work

### 1. Confirm conventions and module boundaries

Read the router registration, admin-token dependency, application-service,
repository, database, startup migration, and concurrency-test implementations
before editing.

Prefer a focused package such as `server/execution/` when it prevents shared
modules from becoming a mixed execution subsystem. Small exports may remain in
shared files when required by repository conventions.

Record the chosen package boundary in the Decision Log before broad
implementation.

### 2. Define explicit state and policy types

Add validated types for:

- work-order approval and lifecycle status;
- execution-run status;
- worker status;
- network policy;
- repository-write policy;
- approval policy.

Terminal-state and transition rules must be explicit and tested. Do not use
unrestricted strings for lifecycle states.

### 3. Add persistence and migration behavior

Persist `WorkOrder`, `Worker`, `CommandManifest`, and `ExecutionRun` identities
separately from existing tasks and leases.

Enforce:

- exact repository and commit identity;
- unique manifest name and version identity;
- one active execution run per work order;
- attempt numbering;
- worker heartbeat and status;
- lifecycle timestamps;
- terminal reason and cleanup metadata placeholders;
- validated capability and policy documents.

Follow existing SQLite compatibility and startup migration conventions. Fresh
and existing databases must both start successfully.

### 4. Implement application services

Add service functions for:

- creating and retrieving work orders;
- approving, rejecting, cancelling, and expiring work orders;
- registering and heartbeating workers;
- capability matching;
- atomically assigning approved queued work;
- creating one active execution run;
- run heartbeat;
- terminal completion;
- lease expiry and safe requeue when policy permits.

Concurrency behavior must be transactionally safe. Do not select a candidate in
one unprotected operation and create its run later.

### 5. Add typed API routes

Expose a cohesive `/api/execution/...` surface following current router
conventions.

Privileged operations include work-order creation, approval, rejection,
cancellation, and manifest administration. Reuse the existing admin-token
dependency unless a narrower Phase 1 worker credential can be added without
expanding scope.

Document any temporary authentication limitation. Do not add OAuth, a hosted
identity provider, or multi-tenant authorization.

### 6. Add tests

Cover:

- valid and invalid exact SHAs;
- manifest identity validation;
- deny-by-default approval;
- capability matches and mismatch reasons;
- atomic checkout with concurrent workers;
- the single-active-run invariant;
- attempt numbering and requeue;
- invalid lifecycle transitions;
- terminal-state immutability;
- heartbeat and expiry;
- cancellation;
- privileged endpoint protection;
- persistence across sessions and startup;
- compatibility with current task, dashboard, and client behavior.

Issue #112 tests must not execute arbitrary commands or depend on Docker,
GitHub network access, or new browser automation.

### 7. Update documentation

Update `docs/API.md` and `docs/message-schema.md` with implemented routes and
payloads. Keep the architecture document aligned with accepted implementation
details.

Do not claim that a worker executes commands until #113 is complete.

## Concrete Steps

1. Fetch and switch to current `main`.
2. Verify a clean checkout and record the exact starting SHA in this plan.
3. Create `feat/execution-plane-contracts` unless branch policy requires another
   name.
4. Inspect the files listed under Context and Orientation.
5. Implement the domain in coherent, reviewable changes.
6. Run targeted tests during development.
7. Run the complete validation suite below.
8. Update every living section of this plan.
9. Push the branch and open a draft PR.
10. Use `Closes #112` only when every acceptance criterion is complete.

## Validation and Acceptance

Run from the repository root:

```bash
python -m pip check
python -m pre_commit run --all-files --show-diff-on-failure
ruff check server client scripts tests web switchboard_cli.py switchboard_client.py
black --check server client scripts tests web switchboard_cli.py switchboard_client.py
mypy --config-file mypy.ini server client scripts
pytest -q
SWITCHBOARD_STRICT_PLAYWRIGHT=1 pytest web/tests/test_ui.py -rA
python -m bandit -q -r server -x server/tests
python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
gitleaks detect --verbose
git diff --check
git status --short
```

Acceptance requires:

- all lifecycle and API tests pass;
- existing task coordination does not regress;
- strict browser tests execute under the supported environment;
- one approved work order is atomically assigned to one eligible worker;
- only one active execution run exists per work order;
- no command-execution code is added;
- no repository-write capability is added;
- typed API documentation is complete;
- the final worktree contains only intentional committed changes.

## Idempotence and Recovery

Database startup and migration behavior must be safe to run repeatedly. Worker
registration with the same identity should refresh capabilities and heartbeat
rather than create uncontrolled duplicates.

If checkout fails, no partial active run or permanently assigned work order may
remain. Tests must prove rollback behavior.

If SQLite cannot enforce an invariant safely, stop and document the exact
limitation before substituting a race-prone application-only check.

The PR must be safe to abandon without affecting `main`. Do not change external
services, secrets, or repository settings.

## Artifacts and Notes

The PR body must include:

- starting and final SHAs;
- changed-file list;
- schema and route summary;
- migration behavior;
- concurrency approach;
- authorization approach and limitations;
- validation commands and results;
- confirmation that command execution and Git writes were not introduced.

Do not commit local databases, logs, coverage HTML, browser traces, or virtual
environments.

## Interfaces and Dependencies

At the end of issue #112, the following conceptual interfaces must exist. Exact
class and function names may follow repository conventions.

- `create_work_order(...) -> WorkOrder`
- `approve_work_order(...) -> WorkOrder`
- `cancel_work_order(...) -> WorkOrder`
- `register_worker(...) -> Worker`
- `heartbeat_worker(...) -> Worker`
- `checkout_execution_work(...) -> ExecutionRun | CheckoutReason`
- `heartbeat_execution_run(...) -> ExecutionRun`
- `complete_execution_run(...) -> ExecutionRun`
- typed request and response contracts for each route;
- repository methods preserving atomic checkout and one-active-run invariants.

No interface in issue #112 accepts arbitrary command text or launches a
process.
