# Add cheapest-capable local worker routing

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

Primary issue: #134. Parent epic: #111. Exact evidence reuse was squash-merged through PR #129 at `7587a77a32e07f180d21cec65881c7868afa0e4d`.

## Purpose / Big Picture

Make local execution routing deliberate when several trusted outbound workers are available. Existing work remains `first_available` by default. An explicitly opted-in `cheapest_capable` work order is assigned only to the deterministic lowest-cost fully capable worker that is healthy, below capacity, actively polling, within the work-order cost ceiling, and able to reserve the required server-owned quota.

This slice remains local-only. It does not call a paid coding agent, provider API, billing system, or external rate-limit endpoint. Cost units are abstract operator-defined comparison units. The user-visible outcome is an auditable route decision showing why one trusted local worker was selected without exposing private machine details or weakening approval, capability, lease, reuse, or evidence controls.

## Progress

- [x] PR #129 squash-merged and issue #121 completed.
- [x] Exact implementation base selected: `7587a77a32e07f180d21cec65881c7868afa0e4d`.
- [x] Issue #134 created with locked product behavior.
- [x] Canonical branch `feat/cheapest-capable-local-routing` created from the exact base.
- [x] Initial living ExecPlan created.
- [x] Preflight verified `origin/main` at `7587a77a32e07f180d21cec65881c7868afa0e4d`, the feature branch and clean isolated worktree at `b1a449ca3851ce19c219e621dd5cddb53e9f27af`, and merge base `7587a77a32e07f180d21cec65881c7868afa0e4d`.
- [x] Audit current worker registration, checkout, capability, lease, persistence, startup, API, and configuration contracts.
- [x] Pre-change baseline recorded: the two required focused groups passed 46 and 14 tests respectively; host `pip check` reported two unrelated global-environment dependency conflicts.
- [x] Lock routing-policy, routing-profile, score, quota, and route-provenance contracts.
- [x] Implement additive restart-safe persistence and privileged profile APIs.
- [x] Implement active-poll tracking and deterministic candidate ranking.
- [x] Implement atomic quota reservation, consumption, release, and reset behavior.
- [x] Integrate routing into checkout without changing default first-available behavior.
- [x] Bind result-affecting routing inputs into execution/reuse policy identity.
- [x] Expose bounded route assessment and historical provenance APIs.
- [x] Add focused contract, concurrency, lifecycle, compatibility, and security tests.
- [x] Update architecture, API, configuration, message-schema, and operator documentation.
- [x] Run the complete protected local matrix, remove generated artifacts, and record exact evidence.
- [ ] Push the focused commits and record the ultimate-head hosted workflow evidence in PR #135's external review record.

## Surprises & Discoveries

- Observation: `ExecutionWorkOrder` already stores legacy `preferred_executor` and floating-point `cost_ceiling` metadata, but checkout does not use either field.
  Evidence: `server/models.py`, `server/execution/service.py`, and `server/execution/repository.py`. New authoritative routing fields must be integer based and additive; the legacy float remains compatibility metadata only.

- Observation: the current pull-based checkout evaluates queued work only against the requesting worker. That preserves outbound-only networking but allows polling order to determine the winner.
  Evidence: `ExecutionService.checkout` and `_checkout_eligible_work`. Cheapest-capable routing therefore needs an authoritative database view of all healthy actively polling workers before allowing the requester to claim.

- Observation: worker heartbeat alone cannot prove that a worker is currently pulling assignments. A healthy but stopped poll loop could otherwise block more expensive active workers indefinitely.
  Evidence: `ExecutionWorker` stores heartbeat and status but no checkout-poll timestamp. Add a server-maintained active-poll signal that workers cannot forge through registration metadata.

- Observation: exact evidence reuse is resolved only after assignment because the worker derives its current environment and dependency-lock identity locally.
  Evidence: issue #121 and `.agent/execplans/011_exact_evidence_reuse.md`. Routing may not claim that a database hint guarantees reuse or weaken same-worker local verification.

- Observation: the repository's execution baseline is green, but the shared host interpreter is not dependency-clean because unrelated globally installed packages conflict with NumPy and Pillow.
  Evidence: pre-change `python -m pip check` reported `opencv-python 4.12.0.88` requiring `numpy<2.3.0` while `numpy 2.3.4` is installed, and `streamlit 1.50.0` requiring `pillow<12` while `pillow 12.3.0` is installed. The required server baseline passed `46 passed, 8 warnings in 29.32s`; the required worker baseline passed `14 passed in 53.26s`.

- Observation: the GitHub exact-PR adapter used legacy `preferred_executor="local"` as descriptive metadata even though no worker with that ID was required to exist.
  Evidence: once #134 made every non-null preferred executor a hard known-worker pin, the existing server-smoke adapter regression failed at work-order creation. The adapter now leaves the pin unset; explicit API pins retain the strict known-worker lifecycle.

- Observation: a zero-unit quota request still needs a conditional profile write to prove that the selected enabled revision remains current between ranking and claim.
  Evidence: the initial implementation returned the loaded revision without touching the profile for zero units. The corrected repository update conditionally matches enabled state, revision, structural quota bounds, and bounded revision headroom, advances the revision, and participates in the same savepoint as capacity, claim, run, and lease creation.

- Observation: file-backed failure injection exposed a response-truth issue after a lost work-order claim or forced run/lease persistence failure.
  Evidence: all mutations correctly rolled back, but checkout discarded `checkout_conflict` and returned `no_queued_work_orders`. The lifecycle now preserves the bounded conflict result while still evaluating older queued orders.

- Observation: focused implementation tests now cover both state-machine behavior and persistence rollback rather than only pure ranking.
  Evidence: the required-plus-routing server group passed `87 passed, 8 warnings in 56.14s`; the required-plus-strict worker group passed `42 passed in 45.05s`. A broader routing/startup/settings/worker contract group passed `98 passed in 36.57s`, and configured Mypy passed all `176` source files.

- Observation: the pinned Bandit `1.8.6` release is not compatible with Python 3.14's AST representation and reports skipped analysis while returning success.
  Evidence: its assertion visitor dereferenced the removed `Constant.s` attribute under Python 3.14. The protected scan was therefore rerun from a clean Python 3.13 environment with the same pinned Bandit release and passed with no findings; the production assertion was also replaced with an explicit bounded exception rather than relying on `assert`.

- Observation: one pre-existing Windows worker-cancellation timing assertion exceeded its 5-second bound once during the first full-suite run.
  Evidence: `test_cancel_running_terminates_process_tree` measured approximately 7.5 seconds on that run. Its exact isolated rerun passed in 2.19 seconds, and the complete suite was restarted and passed `570 passed, 5 skipped` without weakening or reclassifying the gate.

## Decision Log

- Decision: preserve `first_available` as the omitted-policy default.
  Rationale: current callers and validated worker behavior must remain compatible.
  Date/Author: 2026-08-01 / owner and connector planning

- Decision: implement `cheapest_capable` only for trusted local workers in this slice.
  Rationale: provider execution, credentials, pricing, and external rate-limit ingestion require separate product and security decisions.
  Date/Author: 2026-08-01 / owner and connector planning

- Decision: keep worker routing cost and quota profiles operator-owned.
  Rationale: a worker must not win routing by self-reporting a cheaper cost, larger quota, or higher priority through registration or heartbeat payloads.
  Date/Author: 2026-08-01 / connector planning

- Decision: rank eligible workers by integer cost, quota headroom, integer-safe load ratio, operator priority, and worker ID.
  Rationale: the score is stable, explainable, bounded, and independent of process-local iteration order.
  Date/Author: 2026-08-01 / owner and connector planning

- Decision: use recent checkout polling as a separate eligibility signal from heartbeat.
  Rationale: the scheduler must not reserve work for a worker that is healthy but not actually pulling assignments.
  Date/Author: 2026-08-01 / connector planning

- Decision: reserve quota atomically with work-order claim and worker capacity.
  Rationale: independent concurrent checkouts must not overdraw quota or leave partial route state.
  Date/Author: 2026-08-01 / connector planning

- Decision: an explicit preferred executor is a hard operator pin, not a capability bypass.
  Rationale: operator intent should be honored only when the pinned worker remains fully healthy, active, capable, within budget, and within quota.
  Date/Author: 2026-08-01 / owner and connector planning

- Decision: keep unpinned `first_available` independent of routing profiles and active-poll freshness, while requiring the full routed eligibility contract for any explicit pin.
  Rationale: this preserves omitted-policy checkout compatibility and also honors the locked rule that a hard pin cannot bypass profile enablement, health, polling, capacity, capabilities, budget, or quota.
  Date/Author: 2026-08-01 / Codex implementation

- Decision: persist route provenance as bounded scalar fields on both the assigned work order and run, with run quota state authoritative and the work-order copy updated in the same transaction.
  Rationale: normal work-order and run APIs can expose compact provenance without unbounded joins or candidate lists, while guarded SQL can transition reserved quota without relying on JSON predicates.
  Date/Author: 2026-08-01 / Codex implementation

- Decision: profile revision covers operator writes and quota mutations. Every routed assignment conditionally validates and advances the selected enabled profile revision; a non-zero reservation also decrements quota, and a pre-start release advances the revision again.
  Rationale: an operator's expected revision cannot silently overwrite quota activity, and the run can record the exact post-reservation profile revision that owns its reserved units.
  Date/Author: 2026-08-01 / Codex implementation

- Decision: reject a routed assignment before the bounded profile revision can overflow, reserving enough revision headroom for a possible pre-start release.
  Rationale: server-owned revision arithmetic must remain bounded, and a reservation must never be created if its compensating release could not advance the profile safely.
  Date/Author: 2026-08-01 / Codex implementation

- Decision: remove the GitHub adapter's legacy descriptive `"local"` preferred executor rather than weakening hard-pin validation.
  Rationale: an omitted pin preserves the adapter's previous local-worker behavior; a non-null pin now consistently means one exact registered worker throughout the execution API.
  Date/Author: 2026-08-01 / Codex implementation

- Decision: reject profile replacement and quota reset while any run for that worker retains `reserved` quota. Treat a reset with the same reset timestamp and same remaining value as an idempotent no-op; reject older timestamps and same-timestamp conflicting values.
  Rationale: active reservations make replacement ambiguous. Failing closed avoids losing or recreating reserved units, while timestamp equality supplies safe retry behavior and newer resets cannot be overwritten by stale requests.
  Date/Author: 2026-08-01 / Codex implementation

- Decision: use separate bounded server settings for heartbeat freshness and checkout-poll freshness; route assessment is read-only and never refreshes polling.
  Rationale: heartbeats prove liveness, polls prove demand for work, and neither callers nor assessment requests may extend candidacy with an arbitrary interval.
  Date/Author: 2026-08-01 / Codex implementation

## Outcomes & Retrospective

Implementation and the complete protected local matrix are complete. The slice adds one
operator-owned routing-profile table, additive worker/work-order/run columns,
two bounded server freshness settings, strict typed profile/assessment/route
APIs, deterministic integer-only scoring, hard pins, transactional quota
provenance, and worker-side parsing of the new work-order response fields. It
preserves unpinned first-available checkout and the exact-evidence-reuse worker
proof boundary. No provider, paid-agent, credential, billing, browser, MCP,
desktop/RPA, or inbound-listener path was added.

The most valuable test outcome is the file-backed independent-session evidence:
only the cheapest eligible active worker can win one order, and forced losses at
capacity, quota, claim, and after run/lease creation leave capacity, quota,
order, run, and lease state unchanged. Quota tests cover one reservation, one
first-heartbeat consume, idempotent repeated heartbeat, one pre-start release,
stale maintenance retry, new-attempt reservation, no post-start refund, reset
revision/idempotency, and bounded revision overflow. The final full suite passed
`570 passed, 5 skipped`; strict browser tests passed `2 passed`; configured
coverage was 93% aggregate and all 16 module thresholds passed. Dependency,
quality, type, security, secret, link, diff, artifact-cleanup, and public-hygiene
gates are green. Focused commits, the normal push, and ultimate-head hosted
workflow evidence remain to be recorded externally on draft PR #135.

## Context and Orientation

- `server/models.py` defines execution workers, work orders, runs, and leases.
- `server/execution/enums.py` defines lifecycle and evidence-reuse policy values.
- `server/execution/entities.py` defines work-order drafts, worker registration, checkout results, and completion inputs.
- `server/execution/schemas.py` defines strict API request and response contracts.
- `server/execution/capabilities.py` determines whether a worker satisfies trusted and work-order capability requirements.
- `server/execution/repository.py` owns atomic claims, capacity reservations, run/lease creation, stale recovery, and conditional persistence.
- `server/execution/service.py` owns approval, checkout, heartbeat, completion, cancellation, expiry, and evidence/reuse validation.
- `server/api/routers/execution.py` exposes the privileged execution and worker API.
- `server/api/lifecycle.py` provides restart-safe additive SQLite compatibility.
- `server/application/factory.py` and `server/api/dependencies.py` construct and inject the execution service.
- `client/python/execution_worker/client.py` and `worker.py` implement the outbound poll loop.
- `server/tests/test_execution_contracts.py`, `test_execution_concurrency.py`, `test_execution_startup.py`, `test_execution_reuse.py`, and worker server-smoke tests are the primary regression foundations.

## Plan of Work

1. Add strict versioned routing enums and contracts. `RoutingPolicy` must contain `first_available` and `cheapest_capable`. Add bounded route decisions and quota reservation states. Unknown values and extra fields fail validation.

2. Add a separate `WorkerRoutingProfile` persistence model keyed one-to-one by worker ID. Store enabled state, integer estimated cost units per run, integer quota capacity and remaining units, optional aware reset timestamp, bounded integer priority, optimistic revision, and timestamps. The worker registration and heartbeat schemas must not accept these fields.

3. Add privileged operator APIs to create, replace, read, and list profiles. Updates require the expected current revision. Quota reset or replacement must be explicit, bounded, and idempotent; no provider network call or credential is introduced.

4. Extend work orders additively with routing policy, integer maximum cost units, integer required quota units, and a server-derived routing-policy identity/hash if needed. Preserve the existing floating `cost_ceiling` field but do not use it as the authoritative new policy. Validate preferred executor identities and preserve omitted-policy compatibility.

5. Add `last_checkout_poll_at` or an equivalent server-maintained field on workers. Every authenticated checkout attempt updates only the requesting known worker's poll timestamp. Worker-supplied registration and heartbeat payloads may not set it.

6. Add compact route provenance to execution runs. Persist selected worker/profile revision, cost units, required and reserved quota, candidate count, pin state, route reason, policy version, and decision time. Keep candidate lists and private profile internals out of normal responses.

7. Implement active-worker eligibility using authoritative database state: fresh heartbeat, recent poll, online availability, capacity, capabilities, network policy, read-only posture, enabled profile, cost ceiling, quota, and valid pin. Missing or malformed profiles fail closed only for `cheapest_capable`.

8. Implement a deterministic score over eligible workers: lowest cost units; highest quota remaining after reservation; lowest active-load ratio by cross multiplication; lowest priority value; lexical worker ID. Do not use floating point, randomness, process-local locks, or unordered mappings.

9. Integrate routing into checkout. Record the requester's poll first, inspect queued work in stable order, preserve existing `first_available` behavior, and for `cheapest_capable` allow claim only when the requester is the best candidate or valid pin. The work-order claim, worker-capacity reservation, quota reservation, run creation, and lease creation must succeed or roll back together.

10. Add quota reservation lifecycle. Persist reservation state and units. The first valid run heartbeat consumes a reservation. Cancellation or stale lease before start releases it exactly once. Started runs do not refund on completion, failure, timeout, cancellation, or ownership loss. Requeue and reset paths must not double reserve, consume, or release.

11. Bind result-affecting routing policy into `compute_execution_policy_hash` or a focused adjacent canonical hash. Existing evidence produced under materially different routing inputs must not become exact-reuse equivalent. Worker routing profile cost or quota snapshots are route provenance, not deterministic validation-result inputs, unless implementation evidence demonstrates otherwise.

12. Add a privileged route-assessment endpoint for queued work orders. Return only bounded reasons, eligible candidate count, selected worker ID when determinable, cost/quota summary, and pin state. It must not reserve or mutate work beyond explicitly documented poll freshness handling.

13. Add focused tests for compatibility, API strictness, profile ownership, scoring, active polling, pins, cost/quota gates, optimistic updates, independent-session races, quota lifecycle, restart compatibility, route provenance, reuse compatibility, and absence of provider execution.

14. Update `docs/API.md`, `docs/configuration.md`, `docs/architecture/local-execution-broker.md`, `docs/operations/local-worker.md`, and any message-schema or operator documentation needed to explain the local-only routing contract and abstract units.

15. Run the complete protected matrix, remove generated artifacts, audit public content, push only the canonical branch, and keep the PR draft until connector review is complete.

## Concrete Steps

Verify the exact starting state:

```bash
git fetch origin --prune --tags
git worktree list --porcelain
git rev-parse origin/main
git rev-parse origin/feat/cheapest-capable-local-routing
git merge-base origin/main origin/feat/cheapest-capable-local-routing
git status --short --branch
```

The initial main, feature head before this planning commit, and merge base must derive from:

```text
7587a77a32e07f180d21cec65881c7868afa0e4d
```

Use a clean isolated worktree for the existing branch. Stop rather than resetting, rebasing, force-pushing, cleaning uncertain files, or disturbing another worktree.

Before implementation run the existing foundations:

```bash
python -m pip check
python -m pytest -q -p no:cacheprovider \
  server/tests/test_execution_contracts.py \
  server/tests/test_execution_concurrency.py \
  server/tests/test_execution_startup.py \
  server/tests/test_execution_reuse.py
python -m pytest -q -p no:cacheprovider \
  client/python/tests/test_execution_worker_runtime.py \
  client/python/tests/test_execution_worker_server_smoke.py \
  client/python/tests/test_execution_worker_reuse.py
```

During implementation add focused routing modules and tests rather than turning `service.py` or `repository.py` into unbounded mixed-responsibility files. Reasonable focused modules include `server/execution/routing.py` and dedicated routing tests, but preserve repository conventions and avoid speculative abstraction.

Final validation must include:

```bash
python -m pip check
python -m pre_commit run --all-files --show-diff-on-failure
python scripts/dev.py check-todos --root .
python -m ruff check server client scripts tests web switchboard_cli.py switchboard_client.py
python -m black --check server client scripts tests web switchboard_cli.py switchboard_client.py
python -m mypy --config-file mypy.ini server client scripts

mkdir -p reports
python -m pytest --maxfail=1 --disable-warnings --junitxml=reports/pytest.xml
SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py -rA

python -m pytest \
  --cov=server/extensions \
  --cov=server.application.task_service \
  --cov=server.observability \
  --cov=server.application.configuration_service \
  --cov-report=term-missing \
  --cov-report=json:reports/coverage.json

python scripts/dev.py coverage-gate --json reports/coverage.json \
  --module server/extensions/contracts.py=85 \
  --module server/extensions/interfaces.py=85 \
  --module server/extensions/loader.py=85 \
  --module server/extensions/runtime.py=85 \
  --module server/extensions/builtin/task_metrics.py=85 \
  --module server/extensions/builtin/plan_metrics.py=85 \
  --module server/extensions/builtin/plan_latency.py=80 \
  --module server/extensions/builtin/plan_snapshot.py=80 \
  --module server/extensions/builtin/activity_feed.py=85 \
  --module server/extensions/observability.py=80 \
  --module server/observability/diagnostics.py=80 \
  --module server/observability/health.py=85 \
  --module server/observability/activity.py=80 \
  --module server/observability/overview.py=85 \
  --module server/application/task_service.py=75 \
  --module server/application/configuration_service.py=85

python -m bandit -q -r server -x server/tests
python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
gitleaks detect --verbose
mkdir -p lychee
lychee --config lychee.toml --no-progress \
  README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md \
  "docs/**/*.md" --exclude-path docs/history --exclude-path archive
git diff --check
git status --short --branch --untracked-files=all
```

Remove JUnit, coverage, Lychee, browser, database, cache, bytecode, log, and temporary routing/evidence artifacts before staging.

## Validation and Acceptance

Acceptance requires all of the following:

- omitted policy remains `first_available` and existing checkout behavior stays compatible;
- worker registration and heartbeat cannot author routing profiles or poll timestamps;
- privileged profile updates use optimistic revisions and integer bounds;
- `cheapest_capable` considers only healthy, capable, below-capacity, actively polling workers with valid enabled profiles;
- score order and tie-breaks are deterministic and integer safe;
- a cheaper active worker beats a more expensive requester;
- a non-polling worker ages out and cannot starve an active worker indefinitely;
- pins never bypass any eligibility rule;
- claim, capacity, quota, run, and lease persistence is atomic under independent sessions;
- quota cannot overdraw, leak, double reserve, double consume, or double release;
- stale pre-start leases release once, while started outcomes do not refund;
- route provenance is compact, restart-safe, and free of sensitive machine data;
- result-affecting routing inputs alter execution/reuse identity appropriately;
- exact evidence reuse, GitHub exact-PR validation, and default worker execution remain compatible;
- no paid provider, coding agent, billing, or external rate-limit request occurs;
- complete local and hosted protected validation passes.

## Idempotence and Recovery

- Recreate an uncertain worktree rather than cleaning it.
- Never reset, rebase, or force-push the canonical branch.
- Startup compatibility must be safe when columns, tables, or indexes already exist.
- Profile updates and quota resets require expected revisions so retries cannot overwrite newer operator state.
- Conditional quota transitions must be safe to retry and must expose conflicts rather than guessing.
- A failed checkout transaction must leave work order, worker capacity, quota, run, and lease unchanged.
- Generated validation outputs may be deleted and recreated safely.
- If the pull model cannot guarantee the locked score without starvation or partial reservations, preserve evidence and stop for review rather than weakening the contract.

## Artifacts and Notes

Record during implementation:

- exact starting and final SHAs;
- routing schema fields, tables, indexes, and startup compatibility behavior;
- profile CRUD and optimistic-conflict evidence;
- exact score examples and tie-break outcomes;
- active-poll freshness evidence;
- independent-session assignment and quota race results;
- pre-start release and post-start no-refund evidence;
- route-assessment and historical API examples with sensitive fields absent;
- execution/reuse policy hash compatibility results;
- focused and full test counts;
- strict browser and all coverage thresholds;
- quality, security, dependency, secret, link, hygiene, and clean-tree results;
- final hosted Commitlint and CI identifiers in the PR review record using the non-self-referential convention.

Pre-change baseline on 2026-08-01, before production edits:

    python -m pip check
    -> failed only on shared-host packages outside this repository's requirement set:
       opencv-python 4.12.0.88 requires numpy<2.3.0,>=2; installed numpy is 2.3.4
       streamlit 1.50.0 requires pillow<12,>=7.1.0; installed pillow is 12.3.0

    python -m pytest -q -p no:cacheprovider server/tests/test_execution_contracts.py server/tests/test_execution_concurrency.py server/tests/test_execution_startup.py server/tests/test_execution_reuse.py
    -> 46 passed, 8 warnings in 29.32s

    python -m pytest -q -p no:cacheprovider client/python/tests/test_execution_worker_runtime.py client/python/tests/test_execution_worker_server_smoke.py client/python/tests/test_execution_worker_reuse.py
    -> 14 passed in 53.26s

Final validation will use a clean isolated Python environment populated from the repository's pinned development requirements so `pip check` measures this project's dependency graph rather than unrelated shared-host packages.

Post-change local evidence on 2026-08-01:

    python -m pytest -q -p no:cacheprovider server/tests/test_execution_contracts.py server/tests/test_execution_concurrency.py server/tests/test_execution_startup.py server/tests/test_execution_reuse.py server/tests/test_execution_routing.py
    -> 88 passed, 8 warnings in 55.37s after the final typed argument-group refactor

    python -m pytest -q -p no:cacheprovider client/python/tests/test_execution_worker_runtime.py client/python/tests/test_execution_worker_server_smoke.py client/python/tests/test_execution_worker_reuse.py client/python/tests/test_execution_worker_strict_work_order.py
    -> 42 passed in 36.21s after the final typed argument-group refactor

    python -m pip check
    -> No broken requirements found in a clean environment installed from server/requirements-dev.txt

    python -m pre_commit run --all-files --show-diff-on-failure
    python scripts/dev.py check-todos --root .
    python -m ruff check server client scripts tests web switchboard_cli.py switchboard_client.py
    python -m black --check server client scripts tests web switchboard_cli.py switchboard_client.py
    python -m mypy --config-file mypy.ini server client scripts
    -> all passed; Mypy checked 176 source files

    python -m pytest --maxfail=1 --disable-warnings --junitxml=reports/pytest.xml
    -> 570 passed, 5 skipped, 349 warnings in 420.43s on the final local files

    SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py -rA
    -> 2 passed in 9.33s; no strict-mode skip

    configured coverage suite and 16-module coverage gate
    -> 569 passed, 5 skipped; 93% aggregate
       contracts.py 95.40%, interfaces.py 94.17%, loader.py 100%, runtime.py 100%,
       task_metrics.py 92.59%, plan_metrics.py 95%, plan_latency.py 87.76%,
       plan_snapshot.py 100%, activity_feed.py 100%, extensions/observability.py 97.73%,
       diagnostics.py 90.16%, health.py 97.59%, activity.py 94.83%, overview.py 100%,
       task_service.py 90.71%, configuration_service.py 91.30%

    python -m bandit -q -r server -x server/tests
    -> passed under Python 3.13 with repository-pinned Bandit 1.8.6

    python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
    -> no known vulnerabilities

    gitleaks detect --verbose
    -> no leaks across 244 commits and approximately 4.73 MB scanned

    lychee --config lychee.toml --no-progress README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md "docs/**/*.md" --exclude-path docs/history --exclude-path archive
    -> passed; two informational redirects and no link failures

Generated JUnit, coverage, Lychee, browser, database, cache, bytecode, and temporary output under the worktree were removed after validation. Ultimate-head Commitlint and CI workflow identifiers are deliberately not embedded here: after the final head exists, they belong in PR #135's external review record under the established non-self-referential convention.

## Interfaces and Dependencies

Expected focused interfaces include equivalents of:

- `RoutingPolicy` with `first_available` and `cheapest_capable`;
- `QuotaReservationState` and bounded route-reason values;
- operator-owned `WorkerRoutingProfile` persistence and schemas;
- canonical integer-safe routing score helpers;
- active-poll freshness helpers;
- a bounded route assessment/result type;
- atomic repository methods for profile revision, capacity, quota, claim, run, and lease transitions;
- compact run route provenance;
- privileged profile and assessment APIs.

Use the standard library and existing SQLAlchemy/Pydantic stack unless a new dependency is demonstrably necessary. Any new dependency requires separate justification, immutable pinning where applicable, audit evidence, and documentation.
