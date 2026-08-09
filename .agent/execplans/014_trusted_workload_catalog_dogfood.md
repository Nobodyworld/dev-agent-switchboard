# Onboard trusted external workloads and prove real local dogfood

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Switchboard now has an operator-visible Validation Broker, but the trusted execution registry still accepts only `Nobodyworld/dev-agent-switchboard`. This plan turns that single-repository proof into a version-controlled multi-repository workload catalog and demonstrates the result against a real public pull request in `Nobodyworld/app-accounting-modular`.

After this work, an operator should be able to open the dashboard, select an approved repository, see only manifests that are valid for that repository, identify which outbound workers have an operator-configured local checkout for it, resolve a public PR to one exact head, approve the request, execute its fixed quality contract locally, and then reuse the retained evidence on an equivalent request without executing validation steps again.

The feature must remain a trusted execution broker, not a remote shell. Repository and manifest choices are source-controlled. Worker paths remain local. Approval and GitHub publication remain explicit. The first external dogfood validates an existing target PR but must not modify, merge, close, retarget, or mark that PR ready.

## Progress

- [x] 2026-08-09: Issue #138 created from exact `main` `33a5836496fa933dd6aae65ec71238d1b5ac9772`.
- [x] 2026-08-09: Canonical branch `feat/trusted-workload-catalog-dogfood` created from the exact base.
- [x] 2026-08-09: Current registry, worker configuration, command center, routing, and target accounting quality gate inspected.
- [ ] Record baseline local validation before production edits.
- [ ] Implement strict trusted repository/workload catalog while preserving existing manifest digests.
- [ ] Add `validate-accounting-modular@1` with fixed, reviewed, bounded execution steps.
- [ ] Add bounded worker logical-repository availability and restart-safe persistence.
- [ ] Make both routing policies and hard pins repository-aware.
- [ ] Add catalog/readiness APIs and repository-aware command-center onboarding.
- [ ] Add focused catalog, migration, routing, adapter, worker, evidence, and browser regressions.
- [ ] Complete synthetic real-worker fresh-then-reuse proof for the external workload contract.
- [ ] Complete controlled local dogfood against the exact current head of `Nobodyworld/app-accounting-modular` PR #126, or record a precise environment blocker.
- [ ] Update documentation and public-safe screenshot where the UI changes materially.
- [ ] Run the complete protected local matrix and public-hygiene cleanup.
- [ ] Push focused commits to the existing branch and record ultimate-head hosted workflow evidence externally.
- [ ] Keep the PR draft and unmerged pending connector review and separate owner authorization.

## Surprises & Discoveries

- Observation: `server/execution/registry.py` exports `TRUSTED_REPOSITORIES` as a literal one-item frozenset and defines only `worker-smoke@1` and `validate-switchboard@1`.
  Evidence: Current `main` at `33a5836496fa933dd6aae65ec71238d1b5ac9772`.

- Observation: The local worker configuration already supports a mapping of multiple logical `owner/repository` identities to operator-approved absolute canonical checkout paths, but registration sends no bounded logical repository availability to the server.
  Evidence: `client/python/execution_worker/config.py::WorkerConfig.repositories` and `server/execution/entities.py::WorkerRegistration`.

- Observation: The GitHub adapter rejects repositories outside the static set before remote resolution, while normal work-order creation checks only that the repository is in the global set and that the manifest exists; neither boundary verifies an explicit repository-to-manifest association.
  Evidence: `server/github_adapter/service.py::request_validation` and `server/execution/service.py::create_work_order`.

- Observation: `Nobodyworld/app-accounting-modular` has a public draft PR #126 and an authoritative source-controlled quality gate. Its current `src/tools/quality_gate.py` runs Ruff, Ruff format, Mypy, full branch-coverage pytest, aggregate and critical-module coverage gates, focused accounting-control suites, `pip check`, two dependency audits, and a repository secret scan.
  Evidence: target PR #126 and target file `src/tools/quality_gate.py` at observed head `613cf89396c41a0ee3c3aa5886a55c264a38daf0`.

- Observation: The target workflow also contains container and Streamlit gates that are valuable but do not fit the current generic Python worker contract without adding separate Docker/browser worker capability. This first workload should validate the fixed Python quality contract only and report container/attended-browser checks as separate evidence.
  Evidence: `.github/workflows/ci.yml` in `Nobodyworld/app-accounting-modular`.

## Decision Log

- Decision: Deliver repository catalog, worker repository availability, repository-aware routing, command-center onboarding, and first external dogfood in one coherent slice.
  Rationale: Catalog-only infrastructure would not prove practical value; dogfood without catalog enforcement would preserve the one-off architecture. The combined slice produces a complete operator outcome.
  Date/Author: 2026-08-09 / connector planning

- Decision: Keep executable definitions in reviewed source and keep repository-to-manifest compatibility separate from manifest digest calculation.
  Rationale: Existing Switchboard manifest digests are already evidence identities. Display metadata and repository association should not silently rewrite those immutable contracts.
  Date/Author: 2026-08-09 / connector planning

- Decision: Existing worker clients that omit logical repository availability default only to `Nobodyworld/dev-agent-switchboard`.
  Rationale: This preserves historical behavior without allowing an old client to claim every future trusted repository.
  Date/Author: 2026-08-09 / connector planning

- Decision: The worker reports only sorted logical repository names derived from local configuration; absolute paths never cross the worker boundary.
  Rationale: The server needs early routing eligibility but has no reason to know workstation paths.
  Date/Author: 2026-08-09 / connector planning

- Decision: The first accounting manifest represents the target repository's Python quality gate and does not add Docker or attended Edge control to the generic worker.
  Rationale: Docker and physical browser control have different capabilities, resource limits, and threat boundaries. Expanding them here would make the slice unbounded.
  Date/Author: 2026-08-09 / connector planning

- Decision: Real dogfood must not publish a comment to the external target PR without a separate explicit owner action during acceptance.
  Rationale: Validation and remote publication are separate side effects. The Switchboard feature can be proven without surprising another active product PR.
  Date/Author: 2026-08-09 / connector planning

## Outcomes & Retrospective

Pending implementation. At completion, summarize:

- the catalog and compatibility model;
- preserved existing manifest identities;
- external manifest identity and digest;
- worker registration/migration behavior;
- repository-aware route and pin behavior;
- operator onboarding UX;
- synthetic and real external dogfood results;
- exact target SHA, fresh/reused runs, evidence linkage, and canonical-source integrity;
- deferred Docker/browser/MCP/provider boundaries;
- validation totals and any environment limitation.

## Context and Orientation

### Switchboard repository

- `server/execution/registry.py` owns static trusted manifests and the current one-repository allowlist.
- `server/execution/service.py` validates work-order creation, manifest integrity, worker registration, checkout, routing, reuse, leases, and completion.
- `server/execution/routing.py` evaluates and ranks local-worker eligibility.
- `server/execution/entities.py` defines domain inputs including `WorkerRegistration` and `WorkOrderDraft`.
- `server/execution/schemas.py` defines strict API models.
- `server/execution/repository.py` owns persistence and conditional mutations.
- `server/models.py` owns SQLAlchemy tables, including `ExecutionWorker`.
- `server/api/lifecycle.py` performs additive startup compatibility for existing databases.
- `server/api/routers/execution.py` exposes manifests, workers, routing profiles, work orders, runs, evidence, and route assessment.
- `server/api/routers/github_execution.py` exposes exact-PR request, history, status, and explicit publication.
- `server/github_adapter/service.py` resolves GitHub identity and creates normal work orders.
- `client/python/execution_worker/config.py` validates local repository mappings.
- `client/python/execution_worker/models.py` and `client.py` build worker registration and API requests.
- `client/python/execution_worker/worker.py` resolves exact commits, creates disposable worktrees, executes fixed steps, retains evidence, and performs exact local reuse verification.
- `web/static/validation_broker.js` implements repository/manifest selection, worker/profile setup, request lifecycle, history, and operator metrics.
- `web/tests/test_ui.py` is the strict browser acceptance suite.
- `client/python/tests/test_execution_worker_server_smoke.py` contains the production-path real-worker acceptance harness.

### External dogfood repository

The first target is `Nobodyworld/app-accounting-modular` PR #126. Re-resolve all target facts before dogfood. At planning time:

- PR head: `613cf89396c41a0ee3c3aa5886a55c264a38daf0`;
- base branch: `main`;
- source quality entry point: `python -m src.tools.quality_gate`;
- dependency declarations include `requirements-dev.txt` and `requirements-container.lock`;
- full Python quality behavior is defined in `src/tools/quality_gate.py`;
- Docker and attended Edge acceptance are outside this generic-worker profile.

The target checkout is operator-owned and may already exist locally. Never assume its path. The local worker configuration provides the canonical path outside Git history. The Dogfood run must use an exact target commit and a compatible isolated Python environment.

## Plan of Work

### Milestone 1: strict source-controlled catalog

Refactor `server/execution/registry.py` or add a focused `server/execution/catalog.py` so trusted repositories are first-class immutable definitions rather than a literal set.

Introduce a type such as `TrustedRepository` containing only bounded safe metadata and explicit manifest references. Validate the complete catalog at import/startup. Expose helpers similar to:

- `iter_trusted_repositories()`;
- `get_trusted_repository(full_name)`;
- `repository_allows_manifest(full_name, manifest_name, manifest_version)`;
- `trusted_catalog_digest()`.

Keep `TRUSTED_REPOSITORIES` as a derived compatibility export if current imports require it. Do not add executable data to persistence or browser inputs.

Update both `ExecutionService.create_work_order` and `GitHubAdapterService.request_validation` so a globally known manifest cannot be paired with an unauthorized repository. Use bounded error reasons and roll back without records.

Add catalog API schemas and authenticated routes. Safe output may include display metadata, allowed manifest identities and safe metadata, default identity, support status, and catalog digest. It must not include argv or fixed environment values.

### Milestone 2: external accounting manifest

Re-read the target's current PR head, `src/tools/quality_gate.py`, dependency files, coverage configuration, and workflow before defining the manifest.

Add `validate-accounting-modular@1` with fixed shell-free steps. Prefer explicit fixed commands when the same behavior can be represented safely. If invoking `python -m src.tools.quality_gate`, document that this exact reviewed module path is the fixed entry point and that execution is bound to the target exact SHA.

Bind required dependency-lock paths and retained artifacts. Keep step and aggregate output within existing limits. Add parser coverage sufficient to produce compact test, coverage, dependency, and security evidence without returning full local logs.

Add digest and safe-metadata golden tests so future changes are deliberate.

### Milestone 3: logical repository availability

Extend `WorkerRegistration`, strict API schemas, client models, worker registration, `ExecutionWorker`, repository persistence, startup compatibility, and operator projections with `repository_full_names` or an equivalently named bounded sorted list.

The local client derives it from `sorted(config.repositories)`. It never serializes values from the mapping.

For old payloads and existing rows, default only to the historical Switchboard repository. Add prior-schema file-backed tests that start twice, verify the conservative default, then register a new worker list and verify persistence.

Reject malformed, duplicate, unknown, and oversized lists. Define conservative count and item-length limits. Keep the arbitrary worker capability mapping separate and redacted.

### Milestone 4: repository-aware routing

Integrate exact repository availability into capability/eligibility evaluation before any reservation.

Both `first_available` and `cheapest_capable` must exclude workers without the work order's logical repository. Hard pins must fail boundedly with no fallback when unmapped. Route assessment must show a truthful reason and candidate count.

Use file-backed SQLite and independent sessions to prove no partial mutations and no double claim. Preserve same-worker reuse, evidence proof, and exact-object worker preflight.

### Milestone 5: onboarding UX

Update the Validation Broker to load the catalog and render repository options. A repository choice filters allowed manifests and selects the catalog default only when one is defined.

Show repository readiness using bounded worker projections:

- worker logical repository availability;
- activity state;
- profile state;
- route readiness.

Do not show paths. Keep an editable repository field only if necessary for accessible selection, but it must be constrained to catalog options and reject cross-repository manifest combinations.

Update strict Playwright coverage and recapture the synthetic public screenshot if the workspace changes materially.

### Milestone 6: synthetic external workload proof

Extend the real `ExecutionClient`/`LocalWorker` test harness with a minimal synthetic repository that satisfies the accounting manifest contract or with a bounded test-only manifest fixture matching the production external contract.

Prove:

- mapped cheaper worker wins;
- unmapped worker cannot claim;
- all fixed fresh steps execute;
- evidence is retained and compact;
- second equivalent request reuses on the same worker;
- reused step runner count is zero;
- source evidence remains immutable;
- changed SHA/lock/environment/manifest prevents reuse;
- canonical repositories remain clean.

All GitHub behavior remains mocked and offline in automated tests.

### Milestone 7: controlled real dogfood

After code and offline tests pass:

1. Fetch target repository/PR metadata without changing it.
2. Re-resolve target PR #126 exact head and record whether it is still open.
3. Use an existing clean canonical target checkout or create a separate operator-approved clone/worktree outside the Switchboard repository.
4. Ensure the exact target commit object exists locally without altering target branch, remotes, or refs unexpectedly.
5. Create a clean compatible Python environment outside both repositories and install the target's declared development dependencies.
6. Start an isolated Switchboard database/server and one dedicated worker configured with both the Switchboard and target logical repositories as appropriate.
7. Create a routing profile.
8. Create, approve, and execute a fresh target request.
9. Inspect compact evidence and local retained evidence; do not publish externally.
10. Create, approve, and execute the equivalent `allow_exact` request.
11. Prove local verification and zero validation-step execution.
12. Stop all processes, remove only runner-owned temporary worktrees/environments/evidence selected for cleanup, and prove both canonical repositories remain unchanged.

If credentials prevent live exact-PR resolution, use the connector-confirmed exact SHA supplied in the handoff and mark only the GitHub-resolution portion environment-blocked. Do not fabricate publication evidence.

### Milestone 8: docs, final validation, and delivery

Update all operator, API, architecture, configuration, status, and onboarding documentation. Reconcile stale status text left from merged PR #137.

Run focused tests, the complete suite, strict browser, configured coverage thresholds, quality/security/dependency/secret/link checks, cleanup, and public-hygiene scans. Remove generated output.

Use focused Conventional Commits and push normally to the existing branch. Keep the PR draft and unmerged.

## Concrete Steps

### Preflight

From a clean isolated Switchboard worktree for the existing branch:

    git fetch origin --prune --tags
    git status --short --branch --untracked-files=all
    git rev-parse HEAD
    git rev-parse origin/main
    git rev-parse origin/feat/trusted-workload-catalog-dogfood
    git merge-base HEAD origin/main

Require the planning head supplied by GitHub, `origin/main` and merge base `33a5836496fa933dd6aae65ec71238d1b5ac9772`, and no unexplained local changes.

### Baseline focused tests

    python -m pip check
    python -m pytest -q -p no:cacheprovider \
      server/tests/test_execution_contracts.py \
      server/tests/test_execution_startup.py \
      server/tests/test_execution_routing.py \
      server/tests/test_execution_reuse.py \
      server/tests/test_github_adapter_service.py

    python -m pytest -q -p no:cacheprovider \
      client/python/tests/test_execution_worker_strict_work_order.py \
      client/python/tests/test_execution_worker_server_smoke.py \
      client/python/tests/test_execution_worker_reuse.py

    SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py -rA

Record exact baseline results before production edits.

### Complete Switchboard matrix

Use the current workflow and repository-pinned commands. At minimum:

    python -m pip check
    python -m pre_commit run --all-files --show-diff-on-failure
    python scripts/dev.py check-todos --root .
    python -m ruff check server client scripts tests web switchboard_cli.py switchboard_client.py
    python -m black --check server client scripts tests web switchboard_cli.py switchboard_client.py
    python -m mypy --config-file mypy.ini server client scripts
    python -m pytest --maxfail=1 --disable-warnings --junitxml=reports/pytest.xml
    SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py -rA
    python -m bandit -q -r server -x server/tests
    python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
    gitleaks detect --verbose
    git diff --check

Run the configured coverage suite and all existing module thresholds exactly as defined by the repository. Run Lychee over the maintained public Markdown surface.

### Target dogfood validation

Use the exact target source contract at execution time. At planning time the target quality entry point is:

    python -m src.tools.quality_gate

Do not assume this remains unchanged. Re-inspect it before finalizing the manifest and dogfood environment.

Record target repository, PR, exact SHA, Python version, dependency inputs, manifest identity/digest, fresh and reused run IDs, source fingerprint, route provenance, step counts, evidence retention, canonical Git state, and cleanup.

## Validation and Acceptance

The slice is accepted only when all of the following are true:

1. Existing Switchboard manifest digests remain unchanged.
2. Catalog validation and APIs are strict, bounded, and executable-data-free.
3. Direct work orders and GitHub requests reject invalid repository/manifest pairs before persistence.
4. Legacy worker clients/rows default only to Switchboard.
5. New workers advertise logical repository names only.
6. Both routing policies and hard pins exclude unmapped workers atomically.
7. Operator UI repository selection filters compatible manifests and shows safe readiness.
8. Strict browser tests execute with zero skips and no unexpected console errors.
9. Synthetic production-path fresh/reuse tests pass through the real worker.
10. The first external real fresh run succeeds, or a precise environment blocker is recorded without overstating completion.
11. When a fresh external source exists, the second equivalent request reuses it after same-worker local proof with zero validation steps.
12. No external PR publication occurs without separate owner action.
13. Both canonical repositories remain unchanged.
14. Complete local and hosted Switchboard validation is green.
15. Connector review finds no blocker.
16. PR remains draft and unmerged.

## Idempotence and Recovery

- Catalog definitions are static and import-time validated; rerunning startup is read-only except for existing manifest synchronization.
- Additive worker schema compatibility must be safe on every startup and preserve valid repository lists.
- Worker registration is a full authoritative refresh of safe logical names from current local configuration.
- Route assessment is read-only and must not refresh polls or reserve resources.
- Failed checkout attempts roll back capacity, quota, order, run, and lease state.
- Dogfood uses disposable server/database/worktree/evidence roots and a dedicated environment. Cleanup only known runner-owned paths after marker/containment checks.
- Do not reset or clean an interrupted Switchboard or target worktree. Preserve it and report exact state.
- If target PR head moves after resolution, the request remains historical and publication must be stale; do not substitute the new SHA.
- If the target exact commit is unavailable locally, fail with the existing bounded reason and do not fetch or mutate from inside the worker.

## Artifacts and Notes

Planning evidence:

- Switchboard exact base: `33a5836496fa933dd6aae65ec71238d1b5ac9772`.
- Issue: #138.
- Branch: `feat/trusted-workload-catalog-dogfood`.
- First target: `Nobodyworld/app-accounting-modular` PR #126.
- Observed target head during planning: `613cf89396c41a0ee3c3aa5886a55c264a38daf0`.
- Target protected quality entry point during planning: `python -m src.tools.quality_gate`.

Ultimate workflow IDs belong in PR review evidence after the final head exists. Do not create a self-referential evidence commit merely to embed them.

## Interfaces and Dependencies

Expected interfaces may be named differently if repository conventions demand it, but the implementation must provide equivalent strict contracts:

- `TrustedRepository` or `TrustedWorkload` immutable type.
- `iter_trusted_repositories()`.
- `get_trusted_repository(repository_full_name)`.
- `repository_allows_manifest(repository_full_name, manifest_name, manifest_version)`.
- catalog digest/canonical payload helper.
- worker registration field for bounded logical repository names.
- persisted worker logical repository list with restart-safe compatibility.
- routing eligibility reason `worker_repository_unavailable` or an equally bounded documented reason.
- authenticated trusted-repository list/detail schemas and routes.
- repository-aware command-center state and readiness rendering.
- `validate-accounting-modular@1` trusted fixed-argv manifest.

Use the standard library and current FastAPI, Pydantic, SQLAlchemy, pytest, and Playwright stack. Do not add a dependency unless it is demonstrably necessary, pinned, audited, documented, and accepted within issue #138.