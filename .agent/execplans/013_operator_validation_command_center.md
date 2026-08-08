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
- [x] Verify local/remote preflight and establish a clean isolated worktree.
- [x] Run the pre-change focused backend, adapter, worker, and strict-browser baselines.
- [x] Audit current dashboard state, execution APIs, GitHub adapter identity, and persistence upgrade path.
- [x] Lock bounded operator projection and adapter-policy contracts.
- [x] Implement additive adapter policy handling and restart compatibility without adapter schema changes.
- [x] Implement bounded worker, request, overview, and history projection APIs.
- [x] Implement truthful avoided-work aggregation.
- [x] Implement the Validation Broker dashboard workspace and profile-management UX.
- [x] Implement explicit lifecycle and publication controls.
- [x] Add server-backed fresh-then-reused routed GitHub validation proof.
- [x] Add strict browser and accessibility acceptance.
- [x] Add public-safe screenshot and operator documentation.
- [x] Run the complete protected local matrix and public-hygiene audit.
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

- Observation: connector planning review `4888524384` established the canonical branch, draft PR #137, and this vertical-slice contract at the planning head.
  Evidence: the branch began at `e905a3d7020c76d940c0938b2617d55d6d57de7e`; planning-head Commitlint workflow `31249483907` and CI workflow `31249483899` succeeded.

- Observation: the pre-change shared Python 3.14 environment was dependency-dirty even though the focused suites were green.
  Evidence: `python -m pip check` reported unrelated global conflicts for OpenCV versus NumPy and Streamlit versus Pillow, plus a stale invalid `~andit` installation warning. The pre-change backend/adapter matrix passed 169 tests with 8 warnings, the worker matrix passed 36 tests, and strict Playwright passed 2 tests with zero skips.

- Observation: additive GitHub adapter policy does not require a persisted adapter-table column.
  Evidence: the linked `ExecutionWorkOrder` already owns reuse, routing, integer ceiling, quota, and preferred-executor policy. Keeping that record authoritative avoids duplicating mutable state and avoids any `github_validation_requests` schema migration or `schema_version = 1` constraint change.

- Observation: the exact pre-#136 adapter key must remain a separate calculation rather than a partially populated form of the new key.
  Evidence: `_legacy_idempotency_key` preserves the prior canonical input byte-for-byte. Only an all-default request checks it after a new-key miss; a recovered legacy row is returned without changing its immutable key or linked work order.

- Observation: the current-main manifest restart regression remains the relevant prior-schema startup proof because this slice changes no table shape.
  Evidence: `test_main_manifest_schema_survives_repeated_startup` creates the manifest table in its merged-main shape without `updated_at`, runs lifespan twice, resolves/lists the trusted manifest both times, proves one identity, and verifies routing tables and columns remain present. The adapter compatibility regression independently proves legacy default identity recovery without duplication.

- Observation: the first implementation-head Linux matrix ran fast enough for the new hard-bounds ASGI requests to consume the shared default-client rate-limit bucket before a later live-file authentication test.
  Evidence: CI workflow `31279411403` returned `429` instead of the later test's expected `401`, while slower Windows runs remained green. Giving the endpoint test a distinct synthetic ASGI client identity isolates its request accounting without changing production limits, bypass rules, or authentication behavior. The same workflow also confirmed that `list_workers` needs the focused `PLR0913` annotation already used for other typed projection boundaries.

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

- Decision: keep execution policy authoritative on the linked work order and add no adapter persistence.
  Rationale: every new request field already maps to an accepted work-order field, so duplicating it in `github_validation_requests` would introduce drift, a needless prior-schema migration, and a schema-version constraint change without adding recoverability.
  Date/Author: 2026-08-08 / implementation

- Decision: expose one bounded projection module with a 100-row maximum, 10,000 maximum offset, 365-day maximum window, stable request ordering, and redacted worker summaries.
  Rationale: these hard bounds give the browser the joined state it needs without N+1 queries or raw-domain overexposure.
  Date/Author: 2026-08-08 / implementation

- Decision: preserve the existing page shell while rendering the new command center as a visually distinct dark operator workspace.
  Rationale: the final implementation carries the concept's dense scan-friendly metrics and two-column control surface without replacing the existing task, maintenance, configuration, diagnostics, analytics, live-document, or WebSocket UI.
  Date/Author: 2026-08-08 / implementation

## Outcomes & Retrospective

The operator can now complete the complete validation workflow in the existing
dashboard without assembling curl calls: inspect workers and profiles, create or
revision-safely replace a profile, reset quota, request an exact GitHub PR head,
approve/queue or apply another valid lifecycle action, monitor route/run/reuse/
evidence state, explicitly publish current or stale evidence, and review bounded
history and avoided-work metrics. Existing task and operational surfaces remain
in the same page and their strict browser regressions remain green.

The server boundary is one focused read-only projection module plus four bounded
authenticated routes: overview (1-365 UTC days), history and GitHub request lists
(1-100 rows and offsets through 10,000), and worker/profile summaries. Request
history is newest-first by creation time then numeric ID, joins only the latest
run, accepts typed repository/PR/work-order/run/reuse/routing/publication/time
filters, and omits executable, local, private, credential, and unbounded fields.

Every new adapter policy input participates in the new identity. Existing
all-default requests remain recoverable through the exact pre-#136 key and are
returned without mutating identity; non-default requests never use legacy
fallback. Policy is authoritative on the linked work order, so this slice adds
no table column, schema-version change, or migration. The existing merged-main
manifest-shape regression ran lifespan startup twice and remained green.

The offline server-backed proof created a fresh successful run and a distinct
same-worker reused run whose compact evidence contained no validation steps. It
reported one fresh and one reused success, one avoided execution, 7 historical
reference seconds, 3 operator comparison units, and a 50% reuse rate without
double-counting repeat publication. Missing source timing and route cost were
separately proven to contribute zero rather than a guess. Publication was current
before the mocked head moved and stale afterward while preserving the tested SHA.

Strict Playwright passed all three tests with zero skips. The command-center test
proved native malformed-input rejection, server-loaded selectors, UI profile
creation/replacement/quota reset, visible revision conflict recovery, explicit
lifecycle/publication transitions, fresh/reused and current/stale rendering,
disabled-action reasons, keyboard order, zero unexpected console errors, and
page containment at 1440 and 390 pixels. The approved screenshot was generated
from that no-network file-backed application with synthetic public data and was
visually inspected against the generated concept.

The product remains a public developer preview for trusted local networks. MCP,
paid-agent/provider execution, billing, browser/desktop/RPA workers, automatic
approval/publication, webhooks, repository writes, full-log transfer, and
production multi-tenancy remain deliberately out of scope.

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

Current evidence before the complete validation pass:

- preflight: `origin/main` and merge base were `223df7752716dd6ad35e75ba7613eeb03cfb2887`; the local and remote implementation branch began at `e905a3d7020c76d940c0938b2617d55d6d57de7e`; the isolated worktree was clean and exclusively owned the branch;
- pre-change backend/adapter baseline: 169 passed, 8 warnings;
- pre-change worker baseline: 36 passed;
- pre-change strict browser baseline: 2 passed, zero skips;
- implemented server-backed proof: request/work-order/run IDs are database-local synthetic IDs; request 1 completed fresh on the lower-cost worker, request 2 completed as a distinct reused run on the same worker with an empty step list, reference duration 7 seconds, route comparison units 3, one avoided execution, and a 50% reuse rate; publication was current before the mocked head moved and stale afterward;
- focused implementation checks before documentation: the new policy/operator tests passed 4 tests, the adapter/startup target passed 44 tests, and the new strict command-center browser test passed 1 test;
- public screenshot: `docs/assets/switchboard-validation-command-center.png`, captured from the offline file-backed browser application with synthetic public-repository data and inspected against the generated command-center concept; no token, authorization value, path, machine identity, private URL, credential-shaped value, environment value, or financial-savings claim is present;
- final focused backend/adapter/startup matrix: 173 passed with 8 existing SQLAlchemy deprecation warnings;
- final focused worker matrix: 36 passed;
- final strict browser matrix: 3 passed with zero skips in 21.55 seconds;
- complete pytest: 576 passed, 5 documented platform skips, and 344 warnings in 404.09 seconds;
- coverage pytest: the same 576 passed and 5 skipped; aggregate configured coverage was 93%; all 16 gates passed at 95.40%, 94.17%, 100%, 100%, 92.59%, 95%, 87.76%, 100%, 100%, 97.73%, 90.16%, 97.59%, 94.83%, 100%, 90.71%, and 91.30% in workflow order;
- clean Python 3.11 `pip check`, pre-commit, TODO policy, Ruff, Black, Mypy, compatible-interpreter Bandit, pip-audit, Gitleaks over 250 commits, Lychee, and `git diff --check` passed;
- the shared Python 3.14 environment retains the unrelated baseline OpenCV/NumPy and Streamlit/Pillow conflicts. A clean external Python 3.11 environment proved dependency consistency and direct gates. The fixed worker argv `python` resolves the base Astral interpreter ahead of a Windows venv under its intentionally sanitized environment, so the established host interpreter was retained for worker/full pytest while direct Python 3.11 gates used the clean environment; no worker command or trust boundary was weakened;
- generated reports, coverage data, databases, caches, bytecode, link output, and temporary environments are removed before commit. The final public-hygiene audit, local/remote equality, and hosted ultimate-head workflow IDs are recorded during delivery; ultimate-head IDs belong in PR #137's external review record rather than a self-referential plan commit.

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
