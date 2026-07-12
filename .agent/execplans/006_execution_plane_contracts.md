# Add execution-plane contracts and lifecycle APIs

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Switchboard already coordinates high-level agent tasks but cannot safely request deterministic local validation. The first implementation stage adds a separate execution-plane domain: approved work orders, worker capability registration, immutable command-manifest identities, and execution-run lifecycle records.

After this stage, an operator can create and approve a read-only work order for an allowlisted repository and exact Git SHA. One eligible worker can atomically check out the work and create an active execution run. No command is executed in this stage; the observable outcome is a typed, persisted control-plane lifecycle that the local worker in issue #113 can safely consume.

Primary implementation issue: #112. Parent product epic: #111.

## Progress

- [x] Product direction and Phase 1 boundaries settled.
- [x] Architecture decision documented in `docs/architecture/local-execution-broker.md`.
- [x] Phase 1 backlog split into issues #112, #113, and #114.
- [ ] Reconfirm the current `origin/main` SHA and record it here before implementation.
- [ ] Inspect current router, repository, migration, authentication, and test conventions.
- [ ] Add execution-plane enums, schemas, persistence models, and repositories.
- [ ] Add validated lifecycle and capability-matching services.
- [ ] Add `/api/execution/...` routes with appropriate authorization.
- [ ] Add migration/startup compatibility behavior.
- [ ] Add unit, API, concurrency, persistence, and authorization tests.
- [ ] Update API and message-schema documentation.
- [ ] Run complete repository validation.
- [ ] Open a draft PR linked to #112 and update this plan with evidence.

## Surprises & Discoveries

- Observation: The existing `scripts/local_runner.py` is a coordination demonstration only. It checks out a task, maintains a heartbeat, or marks the task complete; it does not execute work.
  Evidence: `scripts/local_runner.py` contains no process, worktree, manifest, artifact, or environment-management implementation.

- Observation: Existing task records contain title, description, dependency, priority, status, and completion notes but do not carry the execution identity or security policy required for local validation.
  Evidence: `TaskIn`, `TaskOut`, and the `Task` SQLAlchemy model in `server/schema.py` and `server/models.py`.

- Observation: Substantial repository work is expected to use a self-contained living ExecPlan.
  Evidence: `.agent/PLANS.md`.

Add implementation discoveries here as they occur. Do not remove failed approaches or unexpected constraints that affect future work.

## Decision Log

- Decision: Keep existing task coordination separate from the new execution-plane domain.
  Rationale: High-level dependency scheduling and deterministic command execution have different lifecycle, security, evidence, retry, and lease semantics. Reusing the task lease tables would create ambiguous ownership and make evidence unreliable.
  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Implement a pull-based worker contract with no inbound workstation listener.
  Rationale: Outbound polling is easier to secure, works behind typical home/network firewalls, and supports future GitHub or MCP request adapters without exposing the local machine.
  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Permit only immutable, trusted command-manifest identities and direct argument-vector execution.
  Rationale: Arbitrary command strings would turn Switchboard into a remote shell and make agent-request approval meaningless.
  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Keep target repositories read-only in Phase 1.
  Rationale: The first economic objective is eliminating paid-agent validation work. Autonomous source changes and Git writes require a separate trust and review model.
  Date/Author: 2026-07-12 / ChatGPT GitHub operator

- Decision: Persist run metadata but keep artifacts under a run-owned storage directory with a configurable 14-day default retention.
  Rationale: Operators need durable audit identity without retaining large logs and browser artifacts indefinitely.
  Date/Author: 2026-07-12 / ChatGPT GitHub operator

## Outcomes & Retrospective

Pending implementation.

At completion, summarize:

- the final model and API surface;
- migration and compatibility decisions;
- concurrency and expiry behavior;
- authorization limitations;
- tests and validation evidence;
- any scope deferred to #113 or #114.

## Context and Orientation

Relevant existing files:

- `server/models.py` defines SQLAlchemy models for agents, tasks, dependencies, leases, files, plan versions, system state, and ExecPlan metadata.
- `server/schema.py` contains the shared Pydantic API contracts.
- `server/application/task_service.py` contains high-level task and lease lifecycle logic.
- `server/infrastructure/repositories.py` provides persistence adapters used by application services.
- `server/api/routers/` contains focused API routers.
- `server/api/lifecycle.py` performs startup and compatibility work for the current database.
- `server/settings.py` contains validated runtime configuration.
- `server/tests/` contains API, service, persistence, security, concurrency, and lifecycle test patterns.
- `docs/API.md` and `docs/message-schema.md` document the public contracts.
- `docs/architecture/local-execution-broker.md` is the accepted product and security boundary.
- `docs/examples/execution/validate-switchboard-v1.yaml` is a contract example for the later worker/evidence stages; it must not be treated as executable in issue #112.

The current task DAG remains authoritative for coordination. The new execution records are additive.

## Plan of Work

### 1. Confirm repository conventions and choose module boundaries

Read the router registration, admin-token dependency, application-service, repository, database, startup migration, and concurrency-test implementations before editing.

Prefer a focused package such as `server/execution/` when it prevents `server/schema.py`, `server/models.py`, or existing task services from becoming a mixed execution subsystem. Small exports may remain in the shared files when required by repository conventions.

Record the chosen package boundary in the Decision Log before broad implementation.

### 2. Define explicit state and policy types

Add enums or equivalent validated types for:

- work-order approval and lifecycle status;
- execution-run status;
- worker status;
- network policy;
- repository-write policy;
- approval policy.

Terminal-state and transition rules must be explicit and unit tested. Do not use unrestricted strings for lifecycle states.

### 3. Add persistence models and migration behavior

Persist `WorkOrder`, `Worker`, `CommandManifest`, and `ExecutionRun` identities separately from existing tasks and leases.

The implementation must enforce:

- exact repository and commit identity;
- unique manifest name/version identity;
- one active execution run per work order;
- attempt numbering;
- worker heartbeat and status;
- lifecycle timestamps;
- terminal reason and cleanup metadata placeholders;
- capability and policy documents using validated JSON where relational columns are not justified.

Follow existing SQLite compatibility and startup migration conventions. A fresh database and an existing database must both start successfully.

### 4. Implement application services

Add service functions for:

- creating and retrieving work orders;
- approving, rejecting, cancelling, and expiring work orders;
- registering and heartbeating workers;
- capability matching;
- atomically assigning one approved queued work order to one eligible worker;
- creating one active execution run;
- run heartbeat;
- terminal completion;
- lease expiry and safe requeue when policy permits.

Concurrency behavior must be transactionally safe. Do not select a candidate in one unprotected operation and create the run later without guarding against a second worker.

### 5. Add typed API routes

Expose a cohesive `/api/execution/...` surface following current router conventions.

Privileged operations include work-order creation, approval, rejection, cancellation, and manifest administration. Reuse the existing admin-token dependency unless a narrower Phase 1 worker credential can be added without expanding scope.

Document any temporary authentication limitation. Do not invent OAuth, a hosted identity provider, or multi-tenant authorization.

### 6. Add tests

Cover:

- valid and invalid exact SHAs;
- manifest identity validation;
- deny-by-default approval;
- capability matching and mismatch reasons;
- atomic checkout with concurrent workers;
- single active run invariant;
- attempt numbering and requeue;
- invalid lifecycle transitions;
- terminal-state immutability;
- heartbeat and expiry;
- cancellation;
- privileged endpoint protection;
- persistence across sessions and startup;
- compatibility with existing task, dashboard, and client behavior.

No test in issue #112 may execute arbitrary commands or depend on Docker, GitHub network access, or a local browser beyond the repository's existing browser suite.

### 7. Update documentation

Update `docs/API.md` and `docs/message-schema.md` with the implemented routes and payloads. Keep `docs/architecture/local-execution-broker.md` aligned with any accepted implementation detail that changes during development.

Do not claim that the worker executes commands until #113 is complete.

## Concrete Steps

1. Fetch and switch to current `main`; verify a clean checkout and record the exact SHA in this plan.
2. Create a branch named `feat/execution-plane-contracts` unless an existing issue branch policy requires another name.
3. Inspect the relevant files listed under Context and Orientation.
4. Implement the domain in small coherent commits or one intentional commit after validation.
5. Run targeted tests during development.
6. Run the complete validation suite below.
7. Update Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective.
8. Push the branch and open a draft PR that links `Closes #112` only when every acceptance criterion is met.

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

- all new lifecycle and API tests passing;
- no regression in existing task coordination;
- strict browser tests executing rather than silently skipping under the supported validation environment;
- an approved work order atomically assigned to one eligible worker;
- one active execution run per work order;
- no command execution code added;
- no repository write capability added;
- complete typed API documentation;
- a clean final worktree except for intentional committed changes.

## Idempotence and Recovery

Database startup and migration behavior must be safe to run repeatedly. Worker registration with the same stable worker identity should update capabilities and heartbeat rather than create uncontrolled duplicates.

If a checkout transaction fails, no partial active run or permanently assigned work order may remain. Tests should prove rollback behavior.

If implementation reveals that SQLite cannot enforce an invariant as designed, stop and document the exact limitation before substituting an application-only race-prone check.

The PR must be safe to abandon without affecting `main`; no external services, secrets, or repository settings are changed.

## Artifacts and Notes

The PR body must include:

- starting and final SHAs;
- changed-file list;
- schema and route summary;
- migration behavior;
- concurrency approach;
- authorization approach and limitations;
- test commands and results;
- explicit confirmation that no command execution or Git write capability was introduced.

Do not commit local databases, logs, coverage HTML, browser traces, or virtual environments.

## Interfaces and Dependencies

At the end of issue #112, the following conceptual interfaces must exist, even if exact class names follow repository conventions:

- `create_work_order(...) -> WorkOrder`
- `approve_work_order(...) -> WorkOrder`
- `cancel_work_order(...) -> WorkOrder`
- `register_worker(...) -> Worker`
- `heartbeat_worker(...) -> Worker`
- `checkout_execution_work(...) -> ExecutionRun | CheckoutReason`
- `heartbeat_execution_run(...) -> ExecutionRun`
- `complete_execution_run(...) -> ExecutionRun`
- typed request/response contracts for each route;
- repository methods that preserve atomic checkout and one-active-run invariants.

No interface in issue #112 accepts arbitrary command text or launches a process.