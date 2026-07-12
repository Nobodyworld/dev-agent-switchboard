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
- [ ] Reconfirm the current `origin/main` SHA before implementation.
- [ ] Inspect router, repository, migration, authentication, and test patterns.
- [ ] Add execution-plane enums, schemas, models, and repositories.
- [ ] Add validated lifecycle and capability-matching services.
- [ ] Add `/api/execution/...` routes with appropriate authorization.
- [ ] Add migration and startup compatibility behavior.
- [ ] Add unit, API, concurrency, persistence, and authorization tests.
- [ ] Update API and message-schema documentation.
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

- Decision: Permit only immutable trusted manifest identities and direct
  argument-vector execution.

  Rationale: Arbitrary command strings would turn Switchboard into a remote
  shell and make approval meaningless.

  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Keep target repositories read-only in Phase 1.

  Rationale: The first objective is eliminating paid-agent validation work.
  Autonomous source changes and Git writes require a separate trust model.

  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Persist run metadata and store artifacts beneath a run-owned path
  with a configurable 14-day default retention.

  Rationale: Operators need durable audit identity without retaining large logs
  and browser artifacts indefinitely.

  Date/Author: 2026-07-12 / ChatGPT GitHub operator

## Outcomes & Retrospective

Pending implementation.

At completion, summarize:

- the final model and API surface;
- migration and compatibility decisions;
- concurrency and expiry behavior;
- authorization limitations;
- tests and validation evidence;
- scope deferred to #113 or #114.

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
