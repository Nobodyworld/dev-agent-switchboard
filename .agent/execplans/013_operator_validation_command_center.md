# Ship the operator validation command center

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

Primary issue: #136. Parent epic: #111. Cheapest-capable local routing was squash-merged through PR #135 at `223df7752716dd6ad35e75ba7613eeb03cfb2887`.

## Purpose / Big Picture

Turn the execution broker from a collection of trusted APIs into a usable operator product.

After this slice, an operator should be able to open the existing Switchboard dashboard and complete one whole local-first validation workflow without stitching together curl commands:

```text
configure worker routing
    -> request validation for a GitHub PR
    -> inspect the exact resolved head
    -> explicitly approve and queue
    -> observe cheapest-capable execution or exact reuse
    -> inspect compact evidence
    -> explicitly publish current or stale evidence
    -> review bounded history and avoided-work metrics
```

The dashboard must preserve existing task, maintenance, configuration, diagnostics, analytics, and live-document behavior. This is a large vertical slice, not a replacement of the existing domains.

The user-visible value is proof that Switchboard can make deterministic local validation genuinely convenient: it resolves exact source identity, chooses a trusted local worker, reuses exact retained evidence when safe, and shows what execution was avoided without claiming unmeasured money or paid-agent credits.

The product remains:

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

## Progress

- [x] PR #135 squash-merged and issue #134 completed.
- [x] Exact base selected: `223df7752716dd6ad35e75ba7613eeb03cfb2887`.
- [x] Issue #136 created as one large end-to-end product slice.
- [x] Canonical branch `feat/operator-validation-command-center` created from the exact base.
- [x] Initial living ExecPlan created.
- [ ] Verify local/remote preflight and establish a clean isolated worktree.
- [ ] Run the pre-change focused backend, adapter, worker, and strict-browser baselines.
- [ ] Audit current dashboard state, execution APIs, GitHub adapter identity, and persistence upgrade path.
- [ ] Lock bounded operator projection and adapter-policy contracts.
- [ ] Implement additive adapter policy persistence and restart compatibility.
- [ ] Implement bounded worker, request, overview, and history projection APIs.
- [ ] Implement truthful avoided-work aggregation.
- [ ] Implement the Validation Broker dashboard workspace and profile-management UX.
- [ ] Implement explicit lifecycle and publication controls.
- [ ] Add server-backed fresh-then-reused routed GitHub validation proof.
- [ ] Add strict browser and accessibility acceptance.
- [ ] Add public-safe screenshot and operator documentation.
- [ ] Run the complete protected local matrix and public-hygiene audit.
- [ ] Push focused commits to the existing branch and require the complete hosted matrix.
- [ ] Complete connector review while keeping PR #137 draft and unmerged.

## Surprises & Discoveries

- Observation: the current dashboard is one long server-served HTML page backed by vanilla JavaScript, HTMX, Tailwind CDN classes, and a small local stylesheet rather than a component framework.
  Evidence: `web/index.html` and `web/static/app.js`. The implementation should extend the established architecture unless a framework migration is independently justified, which is outside this slice.

- Observation: the browser already stores the admin token only in local storage and sends it for protected mutations. That pattern can serve the validation workspace, but the token must never render or enter application state returned by the server.
  Evidence: `ADMIN_TOKEN_STORAGE_KEY`, `loadAdminToken`, and `persistAdminToken` in `web/static/app.js`.

- Observation: existing execution APIs expose work orders, runs, evidence, route provenance, routing-profile CRUD, and lifecycle actions, but their list endpoints are broad primitives rather than a bounded operator projection.
  Evidence: `server/api/routers/execution.py`. A projection layer is preferable to making the browser join several unbounded domain lists.

- Observation: the GitHub adapter creates and reads one request by ID but does not expose a bounded list endpoint, and its create contract currently accepts only repository, PR number, and manifest identity.
  Evidence: `server/api/routers/github_execution.py` and `server/github_adapter/schemas.py`. Optional reuse/routing inputs must be additive, strict, and included in adapter idempotency.

- Observation: the GitHub adapter response already exposes tested head, base SHA, linked work-order status, terminal run, evidence fingerprint, and publication state. The command center can build on this instead of inventing a second lifecycle.
  Evidence: `GitHubValidationRequestOut` in `server/github_adapter/schemas.py`.

- Observation: exact reuse and routed execution already persist source-run provenance, route cost snapshots, quota state, timestamps, and terminal run state. Avoided-work metrics should be derived from those immutable records rather than written into a mutable savings ledger.
  Evidence: `ExecutionRun` route and reuse fields in `server/models.py`.

- Observation: existing strict Playwright tests spin up a real FastAPI application with a file-backed SQLite database and use browser route interception only for deliberately simulated failures.
  Evidence: `web/tests/test_ui.py`. New browser tests should continue exercising the real application wherever possible and use bounded mocks only for GitHub transport-dependent surfaces.

## Decision Log

- Decision: deliver backend projections, operator UX, history, avoided-work metrics, documentation, and end-to-end acceptance in one large vertical PR.
  Rationale: the owner explicitly prefers fewer, larger coherent slices; the value of the execution broker is not obvious until the complete operator loop is visible.
  Date/Author: 2026-08-08 / owner and connector planning

- Decision: retain the existing vanilla HTML/JavaScript dashboard architecture for this slice.
  Rationale: a framework migration would add unrelated build, dependency, and review risk without being required to ship the operator workflow.
  Date/Author: 2026-08-08 / connector planning

- Decision: add bounded operator projections rather than making the browser join raw work-order, run, request, worker, and profile lists.
  Rationale: one server-owned projection can enforce pagination, redaction, stable ordering, and no-double-counting rules consistently.
  Date/Author: 2026-08-08 / connector planning

- Decision: extend the GitHub adapter request with optional reuse and routing policy inputs using compatibility defaults.
  Rationale: the dashboard must be able to request the broker behavior already implemented without creating or mutating work orders through a separate hidden workflow.
  Date/Author: 2026-08-08 / owner and connector planning

- Decision: adapter idempotency must bind every accepted execution-policy input.
  Rationale: two requests with materially different reuse, routing, quota, ceiling, or preferred-worker policy must not collapse into one adapter request.
  Date/Author: 2026-08-08 / connector planning

- Decision: derive avoided-work metrics only from successful reused runs and immutable linked source runs.
  Rationale: this produces an auditable exact count and historical duration estimate without pretending to know actual paid-agent cost.
  Date/Author: 2026-08-08 / owner and connector planning

- Decision: comparison units remain operator-defined routing values, never currency or credits.
  Rationale: the system does not integrate a provider or authoritative billing source.
  Date/Author: 2026-08-08 / owner and connector planning

- Decision: approval and publication remain explicit button actions.
  Rationale: this slice makes the workflow convenient but must not weaken the accepted operator-control boundary.
  Date/Author: 2026-08-08 / owner and connector planning

- Decision: use bounded polling for execution state unless implementation proves a focused execution-event WebSocket materially simplifies the system.
  Rationale: the current APIs are sufficient; a new event transport is not a requirement for the user outcome.
  Date/Author: 2026-08-08 / connector planning

## Outcomes & Retrospective

Pending implementation.

The final retrospective must describe:

- whether the operator can complete the entire workflow without curl;
- the final API and projection boundaries;
- exact adapter-policy and migration behavior;
- fresh versus reused end-to-end evidence;
- avoided-work aggregation semantics and limitations;
- browser/accessibility results;
- screenshot provenance;
- remaining limitations before MCP or paid-provider work.

## Context and Orientation

### Existing operator dashboard

- `web/index.html` contains the complete dashboard markup.
- `web/static/app.js` owns browser state, API helpers, rendering, actions, polling, and WebSocket behavior.
- `web/static/styles.css` contains local styles layered over Tailwind CDN utilities.
- `web/tests/test_ui.py` launches the real FastAPI service and runs strict Playwright acceptance.
- `server/api/routers/ui.py` serves the dashboard document.

The current dashboard already presents:

- system maintenance state;
- configuration;
- diagnostics;
- task analytics;
- task creation and lifecycle;
- live documents.

The new workspace must preserve those surfaces.

### Execution domain

- `server/models.py` defines `ExecutionWorkOrder`, `ExecutionWorker`, `WorkerRoutingProfile`, `ExecutionRun`, and `ExecutionLease`.
- `server/execution/enums.py` defines work-order, run, reuse, routing, quota, worker, and approval states.
- `server/execution/schemas.py` defines strict input/output contracts.
- `server/execution/repository.py` owns database queries and transactional mutations.
- `server/execution/service.py` owns lifecycle, routing, reuse, quota, and evidence validation.
- `server/api/routers/execution.py` exposes authenticated operator and worker routes.
- `server/api/lifecycle.py` provides additive repeated-startup compatibility.

### GitHub adapter

- `server/github_adapter/schemas.py` defines strict create and response contracts.
- `server/github_adapter/service.py` resolves exact PR identity, creates the linked work order, and publishes managed evidence.
- `server/github_adapter/repository.py` owns request persistence.
- `server/github_adapter/transport.py` enforces bounded GitHub transport behavior.
- `server/api/routers/github_execution.py` exposes authenticated request, status, and publish routes.
- `server/models.py` defines `GitHubValidationRequest`.

### Existing test foundations

- `server/tests/test_github_adapter_service.py`
- `server/tests/test_github_adapter_transport.py`
- `server/tests/test_execution_routing.py`
- `server/tests/test_execution_reuse.py`
- `server/tests/test_execution_concurrency.py`
- `server/tests/test_execution_startup.py`
- `client/python/tests/test_execution_worker_server_smoke.py`
- `client/python/tests/test_execution_worker_reuse.py`
- `web/tests/test_ui.py`

## Plan of Work

### 1. Establish exact baseline

Verify the branch and merge base, create or reuse a clean isolated worktree, and run focused baselines for:

- GitHub adapter service/transport/startup;
- execution contracts/routing/reuse/concurrency/startup;
- worker server-smoke/reuse/strict work-order parsing;
- current strict Playwright dashboard tests.

Record exact counts and environment limitations before implementation.

### 2. Extend GitHub adapter policy identity

Add optional strict fields to the adapter request:

```text
reuse_policy
routing_policy
maximum_cost_units
required_quota_units
preferred_executor
```

Compatibility defaults:

```text
never
first_available
null
0
null
```

Update:

- request schema;
- internal request identity;
- idempotency hash;
- persistence or authoritative linked-order recovery;
- work-order creation;
- response projection where useful;
- prior-schema repeated-startup compatibility;
- tests for every policy dimension.

Do not accept manifest parameters, commands, paths, environment values, or credentials.

### 3. Add bounded read models

Create a focused operator projection module, likely under `server/execution/` or `server/application/`, rather than expanding already-large lifecycle methods without structure.

Define typed outputs for:

- overview metrics;
- worker/profile summaries;
- GitHub request list items;
- history rows;
- paginated metadata;
- current request detail when a joined projection materially reduces client calls.

Use stable ordering and explicit hard bounds.

Suggested history row fields:

```text
request ID
repository and PR number
tested head SHA
manifest identity
work-order ID/status
terminal/latest run ID/status
routing policy and selected worker
estimated cost units
reuse decision and source run
run duration
evidence fingerprint
publication state/decision
created/updated timestamps
```

No full logs, artifact bytes, commands, argv, local paths, environments, private URLs, or credentials may enter the projection.

### 4. Implement overview aggregation

Derive metrics from authoritative persisted records within a caller-supplied bounded window.

At minimum calculate:

- request counts;
- work-order status counts;
- run status counts;
- fresh successful runs;
- reused successful runs;
- unavailable exact reuse;
- deterministic executions avoided;
- reused source-duration sum where source timing is complete;
- comparison units avoided where the reused run has a route cost snapshot;
- reuse rate;
- current/stale publication counts;
- active/stale/capacity-constrained worker counts.

Do not double-count:

- multiple attempts for one work order in work-order counts;
- publication updates;
- source runs themselves as avoided executions;
- reused runs without successful terminal state;
- missing source timing or missing cost snapshots.

### 5. Add operator APIs

Add authenticated typed endpoints equivalent to:

```text
GET /api/execution/operator/overview
GET /api/execution/operator/history
GET /api/execution/workers
GET /api/execution/github/requests
```

Use explicit bounds for limit, offset/cursor, time window, and filters.

The request-list endpoint should return bounded joined lifecycle state without forcing N+1 client calls.

Preserve existing routes and response compatibility.

### 6. Build the Validation Broker workspace

Extend `web/index.html` with accessible sections or tabs for:

- broker overview cards;
- new GitHub PR validation form;
- request detail and lifecycle actions;
- worker/routing-profile management;
- execution history and filters.

Extend `web/static/app.js` with focused state and render functions. Avoid one monolithic function where small modules or grouped functions improve reviewability without a framework migration.

The form should load manifest and worker choices from the server.

Actions must include:

- request validation;
- approve;
- approve and queue;
- queue;
- cancel;
- expire;
- refresh;
- publish evidence;
- create/replace routing profile;
- reset quota.

Only render actions allowed by the current lifecycle state. Confirm destructive transitions.

### 7. Monitor and explain state

Show exact head, route, quota, run, reuse, evidence, and publication state with concise badges and a timeline.

Use bounded polling with cleanup when the page unloads. Do not create uncontrolled request loops.

Display conflict and stale responses through existing toast patterns plus persistent inline status where the operator needs recovery guidance.

### 8. Implement history and avoided-work UX

Add cards for:

- deterministic executions avoided;
- reference execution time avoided;
- comparison units avoided;
- fresh runs;
- reused runs;
- reuse rate;
- current/stale publications.

Use explicit labels and help text that comparison units are not money or measured paid-agent credits.

Add a filterable table with exact SHA copy controls and fresh/reused/current/stale badges.

### 9. Add end-to-end server proof

Use mocked GitHub transport and existing server-backed worker helpers to prove:

1. two workers and profiles;
2. cheapest-capable selection;
3. fresh successful evidence;
4. current publication;
5. second exact policy request;
6. local exact reuse without validation steps;
7. correct overview/history metrics;
8. moved-head stale publication.

The proof must remain offline and use no real credentials.

### 10. Add strict browser acceptance

Extend Playwright tests for the principal workflow, responsiveness, keyboard navigation, disabled action reasons, optimistic conflicts, fresh/reused history, and current/stale publication.

Use strict mode and require zero skips.

Test at least one desktop and one narrow viewport for horizontal containment.

### 11. Documentation and screenshot

Update README, API, architecture, configuration, local-worker operations, public status, and a focused command-center guide.

Capture a public-safe screenshot only from synthetic local data. Inspect it for:

- no token;
- no local path;
- no machine identity;
- no private URL;
- no real credential-shaped value;
- no misleading actual-savings claim.

### 12. Complete validation and delivery

Run focused tests first, then the full protected matrix. Remove generated artifacts. Audit public changes. Commit in intentional functional groups. Push normally to the existing branch. Keep the PR draft until connector review is complete.

## Concrete Steps

### Preflight

From the primary checkout, inspect only:

```powershell
git fetch origin --prune --tags
git status --short --branch --untracked-files=all
git worktree list --porcelain
git rev-parse origin/main
git rev-parse origin/feat/operator-validation-command-center
git merge-base origin/main origin/feat/operator-validation-command-center
```

Require:

```text
origin/main: 223df7752716dd6ad35e75ba7613eeb03cfb2887
starting branch head: <planning head created by the connector>
merge base: 223df7752716dd6ad35e75ba7613eeb03cfb2887
```

Use a clean isolated worktree. Do not switch, reset, clean, or alter an unrelated primary checkout.

### Focused baselines

Run at minimum:

```powershell
python -m pip check

python -m pytest -q -p no:cacheprovider `
  server/tests/test_github_adapter_service.py `
  server/tests/test_github_adapter_transport.py `
  server/tests/test_execution_startup.py `
  server/tests/test_execution_contracts.py `
  server/tests/test_execution_routing.py `
  server/tests/test_execution_reuse.py `
  server/tests/test_execution_concurrency.py

python -m pytest -q -p no:cacheprovider `
  client/python/tests/test_execution_worker_server_smoke.py `
  client/python/tests/test_execution_worker_reuse.py `
  client/python/tests/test_execution_worker_strict_work_order.py

$env:SWITCHBOARD_STRICT_PLAYWRIGHT = "1"
python -m pytest web/tests/test_ui.py -rA
```

### Expected implementation files

The actual design determines the final set, but likely files include:

```text
server/models.py
server/api/lifecycle.py
server/api/routers/execution.py
server/api/routers/github_execution.py
server/api/__init__.py
server/execution/entities.py
server/execution/schemas.py
server/execution/repository.py
server/execution/service.py
server/execution/operator_projection.py
server/github_adapter/schemas.py
server/github_adapter/repository.py
server/github_adapter/service.py
web/index.html
web/static/app.js
web/static/styles.css
web/tests/test_ui.py
server/tests/test_execution_operator_projection.py
server/tests/test_github_adapter_service.py
server/tests/test_execution_startup.py
client/python/tests/test_execution_worker_server_smoke.py
docs/API.md
docs/configuration.md
docs/architecture/local-execution-broker.md
docs/operations/local-worker.md
docs/operations/validation-command-center.md
docs/reports/status.md
README.md
```

Do not treat this as permission for unrelated edits.

### Complete local matrix

Run the repository's current protected commands, including:

```powershell
python -m pip check
python -m pre_commit run --all-files --show-diff-on-failure
python scripts/dev.py check-todos --root .
python -m ruff check server client scripts tests web switchboard_cli.py switchboard_client.py
python -m black --check server client scripts tests web switchboard_cli.py switchboard_client.py
python -m mypy --config-file mypy.ini server client scripts

New-Item -ItemType Directory -Force reports | Out-Null
python -m pytest --maxfail=1 --disable-warnings --junitxml=reports/pytest.xml

$env:SWITCHBOARD_STRICT_PLAYWRIGHT = "1"
python -m pytest web/tests/test_ui.py -rA
```

Run the configured coverage suite and all existing module thresholds exactly as defined by the current workflow and prior ExecPlans.

Also run:

```powershell
python -m bandit -q -r server -x server/tests
python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
gitleaks detect --verbose

New-Item -ItemType Directory -Force lychee | Out-Null
lychee --config lychee.toml --no-progress `
  README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md `
  "docs/**/*.md" `
  --exclude-path docs/history `
  --exclude-path archive

git diff --check
git status --short --branch --untracked-files=all
```

Use the established compatible interpreter for pinned tools when the host interpreter has a documented tool incompatibility. Do not silently accept a scanner that skipped analysis.

## Validation and Acceptance

The slice is accepted only when all of the following are proven:

1. Existing callers omit new adapter fields and retain current defaults.
2. Every policy input changes adapter idempotency when it should.
3. Existing adapter databases upgrade and start twice without duplication or data loss.
4. Worker/profile APIs are bounded and do not allow worker-owned profile writes.
5. Overview and history are paginated, stably ordered, and redacted.
6. Avoided execution count equals successful reused runs only.
7. Source-duration estimate uses the linked immutable source run only.
8. Missing source duration or route cost is excluded rather than guessed.
9. The dashboard can request, approve, queue, monitor, and publish a validation.
10. The dashboard can create/update a profile and handle revision conflicts.
11. Fresh and reused runs display distinctly.
12. Current and stale publication display distinctly.
13. A real server-backed offline fresh-then-reused flow passes.
14. Existing task dashboard behavior remains green.
15. Strict browser tests execute with zero skips.
16. Desktop and narrow viewport containment pass.
17. A public-safe screenshot contains only synthetic data.
18. Full local and hosted matrices pass.
19. Public-hygiene review finds no credential, path, machine, private URL, log, database, report, or cache leakage.
20. PR #137 remains draft and unmerged pending connector review.

## Idempotence and Recovery

- Adapter schema changes must use idempotent repeated-startup compatibility.
- Projection endpoints are read-only and safe to retry.
- List/history pagination must not mutate last-seen state.
- Route assessment must not refresh worker poll timestamps unless the accepted implementation explicitly documents and tests a change; the current preference is no mutation.
- UI polling must cancel prior timers and tolerate repeated refresh.
- Optimistic profile conflicts must refresh state rather than overwrite a newer revision.
- Repeated request submission with identical full identity should return the existing adapter request.
- Publication remains idempotent under the managed-comment contract.
- The screenshot must be regenerated only after the final UI state is stable.
- If implementation stops, preserve the isolated worktree and report local/remote SHAs plus every dirty path. Do not reset, clean, stash, or recreate the branch.

## Artifacts and Notes

Record during implementation:

- exact preflight SHAs;
- baseline counts;
- adapter schema before/after and prior-schema test;
- example bounded overview/history payloads using synthetic values;
- fresh and reused run IDs from the server-backed proof;
- source duration and comparison-unit calculations;
- strict browser counts and viewport evidence;
- screenshot path and exact tested SHA;
- full pytest count;
- aggregate and module coverage;
- security, dependency, secret, and link results;
- public-hygiene result;
- final local/remote SHA equality;
- final hosted Commitlint and CI IDs in PR #137's external review record.

## Interfaces and Dependencies

Expected new or extended interfaces include equivalents of:

```python
class GitHubValidationCreateIn:
    reuse_policy: ReusePolicy = ReusePolicy.NEVER
    routing_policy: RoutingPolicy = RoutingPolicy.FIRST_AVAILABLE
    maximum_cost_units: int | None = None
    required_quota_units: int = 0
    preferred_executor: str | None = None

class ExecutionOperatorOverviewOut:
    window: TimeWindowOut
    requests: RequestMetricsOut
    work_orders: WorkOrderMetricsOut
    runs: RunMetricsOut
    avoided_work: AvoidedWorkMetricsOut
    publications: PublicationMetricsOut
    workers: WorkerMetricsOut

class ExecutionHistoryPageOut:
    items: list[ExecutionHistoryItemOut]
    limit: int
    offset: int
    total: int
```

Names may change to fit repository conventions, but contracts must remain typed, bounded, and strict.

No new runtime dependency is expected. Any dependency addition requires explicit justification, pinning, license review, audit evidence, and documentation.
