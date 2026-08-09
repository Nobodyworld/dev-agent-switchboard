# Onboard trusted external workloads and prove real local dogfood

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept current as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Switchboard now has an operator-visible Validation Broker, but the trusted registry still accepts only `Nobodyworld/dev-agent-switchboard`. This slice turns that self-validation proof into a version-controlled multi-repository workload catalog and demonstrates it against a real public pull request in `Nobodyworld/app-accounting-modular`.

After completion, an operator can select an approved repository, see only compatible trusted manifests, identify workers that have an operator-configured local checkout for it, resolve a PR to an exact head, approve the request, execute its fixed quality contract locally, and reuse retained evidence on an equivalent request without running validation steps again.

The product remains a trusted execution broker, not a remote shell. Repository and manifest definitions stay in reviewed source. Worker paths remain local. Approval and GitHub publication stay explicit. The external target PR must not be modified, merged, closed, retargeted, or marked ready by this slice.

## Progress

- [x] Issue #138 created from exact `main` `33a5836496fa933dd6aae65ec71238d1b5ac9772`.
- [x] Branch `feat/trusted-workload-catalog-dogfood` created from the exact base.
- [x] Current registry, worker configuration, routing, command center, and target accounting quality gate inspected.
- [ ] Record baseline local validation before production edits.
- [ ] Implement a strict trusted repository/workload catalog while preserving existing manifest digests.
- [ ] Add `validate-accounting-modular@1` with fixed reviewed argv and bounded evidence.
- [ ] Add bounded worker logical-repository availability and restart-safe persistence.
- [ ] Make both routing policies, hard pins, assessment, and exact reuse repository-aware.
- [ ] Add catalog/readiness APIs and repository-aware command-center onboarding.
- [ ] Add focused catalog, migration, routing, adapter, worker, evidence, and browser regressions.
- [ ] Complete a production-path synthetic fresh-then-reuse proof for the external workload contract.
- [ ] Complete controlled local dogfood against the exact current head of `Nobodyworld/app-accounting-modular` PR #126, or record a precise environment blocker.
- [ ] Update authoritative docs and the public-safe screenshot where needed.
- [ ] Run the complete protected local matrix, cleanup, and public-hygiene audit.
- [ ] Push focused commits, record ultimate-head hosted evidence externally, and keep PR #139 draft and unmerged.

## Surprises & Discoveries

- Observation: `server/execution/registry.py` exports `TRUSTED_REPOSITORIES` as a literal one-item frozenset and defines only `worker-smoke@1` and `validate-switchboard@1`.
  Evidence: current `main` at `33a5836496fa933dd6aae65ec71238d1b5ac9772`.

- Observation: `WorkerConfig.repositories` already supports multiple logical `owner/repository` identities mapped to local canonical paths, but worker registration sends no bounded logical repository list to the server.
  Evidence: `client/python/execution_worker/config.py` and `server/execution/entities.py`.

- Observation: normal work-order creation and the GitHub adapter validate a global repository set and a global manifest registry, but neither boundary enforces an explicit repository-to-manifest association.
  Evidence: `server/execution/service.py` and `server/github_adapter/service.py`.

- Observation: public `Nobodyworld/app-accounting-modular` PR #126 has a source-controlled Python quality gate covering Ruff, formatting, Mypy, full pytest with branch coverage, aggregate and critical-module coverage gates, focused accounting controls, `pip check`, dependency audits, and secret scanning.
  Evidence: target `src/tools/quality_gate.py` at observed head `613cf89396c41a0ee3c3aa5886a55c264a38daf0`.

- Observation: the target also has Docker and attended Edge gates, but those require separate worker capabilities and remain outside this generic Python workload profile.
  Evidence: target `.github/workflows/ci.yml` and PR #126.

## Decision Log

- Decision: Deliver catalog, worker repository availability, repository-aware routing, command-center onboarding, and first external dogfood in one coherent slice.
  Rationale: Catalog-only infrastructure would not prove utility; dogfood without catalog enforcement would preserve a one-off architecture.
  Date/Author: 2026-08-09 / connector planning

- Decision: Keep executable definitions in reviewed source and keep repository association separate from existing manifest digest calculation.
  Rationale: Current manifest digests are evidence identities and must not change because of display metadata or repository catalog structure.
  Date/Author: 2026-08-09 / connector planning

- Decision: Legacy workers that omit repository availability default only to `Nobodyworld/dev-agent-switchboard`.
  Rationale: This preserves historical behavior without allowing old clients to claim future repositories.
  Date/Author: 2026-08-09 / connector planning

- Decision: Workers report only sorted logical repository names derived from local config; absolute paths never cross the worker boundary.
  Rationale: The server needs early routing eligibility, not workstation paths.
  Date/Author: 2026-08-09 / connector planning

- Decision: The first accounting manifest covers the target Python quality gate but not Docker or attended browser execution.
  Rationale: Those are separate capability and threat boundaries and would make this slice unbounded.
  Date/Author: 2026-08-09 / connector planning

- Decision: Real dogfood must not publish to the external PR without a separate explicit owner action.
  Rationale: Validation and remote publication are distinct side effects.
  Date/Author: 2026-08-09 / connector planning

## Outcomes & Retrospective

Pending implementation. At completion, summarize catalog compatibility, preserved manifest identities, the external manifest digest, migration behavior, repository-aware routing, onboarding UX, synthetic and real dogfood results, exact target SHA, fresh/reused evidence linkage, canonical-source integrity, deferred worker types, validation totals, and any environment blocker.

## Context and Orientation

### Switchboard

- `server/execution/registry.py`: trusted manifests and current repository allowlist.
- `server/execution/service.py`: work-order validation, registration, checkout, routing, reuse, leases, and completion.
- `server/execution/routing.py`: eligibility and deterministic ranking.
- `server/execution/entities.py` and `schemas.py`: domain and API contracts.
- `server/execution/repository.py`, `server/models.py`, and `server/api/lifecycle.py`: persistence and restart compatibility.
- `server/api/routers/execution.py`: manifests, workers, profiles, work orders, runs, evidence, and route assessment.
- `server/github_adapter/service.py`: exact GitHub identity resolution and work-order creation.
- `client/python/execution_worker/config.py`, `models.py`, `client.py`, and `worker.py`: local config, registration, execution, evidence, and exact local reuse.
- `web/static/validation_broker.js` and `web/tests/test_ui.py`: operator workflow and strict browser acceptance.
- `client/python/tests/test_execution_worker_server_smoke.py`: real `ExecutionClient`/`LocalWorker` acceptance harness.

### External dogfood target

Re-resolve all target facts immediately before execution. At planning time:

- repository: `Nobodyworld/app-accounting-modular`;
- PR: #126;
- observed head: `613cf89396c41a0ee3c3aa5886a55c264a38daf0`;
- Python quality entry point: `python -m src.tools.quality_gate`;
- dependency inputs include `requirements-dev.txt` and `requirements-container.lock`.

Never assume a local path. The operator-owned worker config provides the canonical checkout path outside Git history. Dogfood must use an exact commit and a compatible isolated Python environment.

## Plan of Work

### 1. Strict source-controlled catalog

Refactor `server/execution/registry.py` or add `server/execution/catalog.py` with an immutable `TrustedRepository`-style contract. Validate canonical unique repository identities, explicit allowed manifest references, a valid optional default, bounded display metadata, and deterministic catalog serialization/digest.

Provide helpers equivalent to:

- `iter_trusted_repositories()`;
- `get_trusted_repository(full_name)`;
- `repository_allows_manifest(full_name, name, version)`;
- `trusted_catalog_digest()`.

Keep `TRUSTED_REPOSITORIES` only as a derived compatibility export. Update direct work-order creation and the GitHub adapter so cross-repository manifest use fails before persistence. Add bounded authenticated catalog list/detail APIs that never expose argv, environment values, local paths, credentials, or arbitrary capability documents.

### 2. External accounting manifest

Re-read the target's current PR head, quality gate, dependency files, coverage config, and workflow before defining `validate-accounting-modular@1`.

Use fixed shell-free argv. Prefer explicit fixed steps; invoking a reviewed fixed target module is acceptable only when documented and bound to the exact target SHA. Bind required capabilities, timeouts, network/read-only policy, dependency-lock paths, artifacts, parsers, and result contract. Add digest and safe-metadata golden tests.

### 3. Logical repository availability

Extend worker registration, strict API schemas, client registration, `ExecutionWorker`, persistence, startup compatibility, and operator projections with a bounded sorted logical repository list.

The client derives it from `sorted(config.repositories)`. No values from the path mapping are serialized. Old payloads and existing rows default only to Switchboard. Reject malformed, duplicate, unknown, and oversized lists. Add prior-schema file-backed startup tests that run twice and prove persistence.

### 4. Repository-aware routing

Require the exact work-order repository in worker availability for `first_available`, `cheapest_capable`, hard pins, route assessment, fresh execution, and exact reuse. Exclude unmapped workers before capacity/quota mutation and return a bounded reason such as `worker_repository_unavailable`.

Use file-backed SQLite and independent sessions to prove no partial mutation, truthful candidate counts, no double claim, and unchanged same-worker reuse rules. Registration metadata is only an eligibility signal; worker-local exact-object checks remain authoritative.

### 5. Command-center onboarding

Load trusted repositories from the server, filter manifests by repository, show the default explicitly, and show which workers advertise the repository plus bounded activity/profile readiness. Never show paths. Preserve explicit approval/publication and existing request, route, quota, evidence, history, accessibility, token-redaction, and responsive behavior.

A read-only readiness projection may be added, but it must not reserve resources, refresh polls, resolve arbitrary URLs, fetch source, or claim the commit exists locally.

### 6. Synthetic external production-path proof

Extend the real worker harness with a minimal compatible target fixture or bounded test-only contract matching the production manifest. Prove mapped routing, unmapped refusal, fresh step execution, retained compact evidence, second-request same-worker local reuse with zero step execution, source immutability, changed-input invalidation, and clean canonical repositories. Automated GitHub behavior remains mocked and offline.

### 7. Controlled real dogfood

After offline tests pass:

1. Re-resolve target PR #126 and record its exact current head/state.
2. Use an existing clean operator-approved canonical checkout or create a separate clone outside both repositories.
3. Ensure the exact target object exists locally without altering active branches or source.
4. Create an isolated compatible Python environment outside both repositories and install target dependencies.
5. Start an isolated Switchboard database/server and a dedicated real worker configured for the target logical repository.
6. Create a routing profile and explicitly approve a fresh `never` request.
7. Execute the external manifest, retain evidence, and prove target integrity.
8. Create and explicitly approve the equivalent `allow_exact` request.
9. Prove local verification, distinct run/source linkage, and zero validation steps on reuse.
10. Stop processes and clean only known runner-owned resources.

Do not publish to the target PR. If live GitHub credentials are absent, execute against a connector-confirmed exact SHA and mark only GitHub resolution/publication environment-blocked.

### 8. Documentation and delivery

Update `README.md`, API, configuration, architecture, local-worker operations, command-center operations, status report, a new trusted-workload onboarding guide, and this plan. Reconcile stale status text left from merged PR #137.

Run focused tests, the complete suite, strict browser, configured coverage thresholds, quality/security/dependency/secret/link checks, cleanup, and public-hygiene scans. Push focused Conventional Commits normally to the existing branch. Keep PR #139 draft and unmerged.

## Concrete Steps

### Preflight

    git fetch origin --prune --tags
    git status --short --branch --untracked-files=all
    git rev-parse HEAD
    git rev-parse origin/main
    git rev-parse origin/feat/trusted-workload-catalog-dogfood
    git merge-base HEAD origin/main

Require the exact planning head, `origin/main` and merge base `33a5836496fa933dd6aae65ec71238d1b5ac9772`, and no unexplained local changes.

### Baseline focused tests

    python -m pip check
    python -m pytest -q -p no:cacheprovider server/tests/test_execution_contracts.py server/tests/test_execution_startup.py server/tests/test_execution_routing.py server/tests/test_execution_reuse.py server/tests/test_github_adapter_service.py
    python -m pytest -q -p no:cacheprovider client/python/tests/test_execution_worker_strict_work_order.py client/python/tests/test_execution_worker_server_smoke.py client/python/tests/test_execution_worker_reuse.py
    SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py -rA

Record exact results before production edits.

### Complete Switchboard matrix

Use the current repository-pinned commands. At minimum:

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

### Target dogfood

Re-inspect the target before finalizing the manifest. At planning time its entry point is:

    python -m src.tools.quality_gate

Record target repository, PR, exact SHA, Python version, dependency inputs, manifest identity/digest, fresh and reused run IDs, source fingerprint, route provenance, step counts, evidence retention, canonical Git state, and cleanup.

## Validation and Acceptance

Acceptance requires:

1. Existing Switchboard manifest digests remain unchanged.
2. Catalog validation and APIs are strict, bounded, and executable-data-free.
3. Direct work orders and GitHub requests reject invalid repository/manifest pairs before persistence.
4. Legacy workers/rows default only to Switchboard.
5. New workers advertise logical repository names only.
6. Both routing policies and hard pins exclude unmapped workers atomically.
7. The UI filters compatible manifests and shows safe readiness.
8. Strict browser tests run with zero skips and no unexpected console errors.
9. Synthetic production-path external fresh/reuse tests pass through the real worker.
10. A real external fresh run succeeds, or a precise environment blocker is recorded without overstating completion.
11. With a valid fresh source, the second request reuses after same-worker local proof with zero validation steps.
12. No external publication occurs without separate owner action.
13. Both canonical repositories remain unchanged.
14. Complete local and hosted Switchboard validation is green.
15. Connector review finds no blocker.
16. PR #139 remains draft and unmerged.

## Idempotence and Recovery

- Catalog definitions are static and import-time validated.
- Worker schema upgrades must be repeatable and preserve valid lists.
- Registration fully refreshes logical names from current local config.
- Readiness/assessment performs no reservation or poll refresh.
- Failed checkout rolls back capacity, quota, order, run, and lease state.
- Dogfood uses dedicated temporary server/database/worktree/evidence/environment roots; cleanup only marker-verified runner-owned paths.
- Never reset or clean interrupted Switchboard or target worktrees. Preserve and report exact state.
- A moved target head remains historical and any later publication must be stale; never substitute a SHA.
- Missing local commit objects fail boundedly and do not trigger worker-side fetch or source mutation.

## Artifacts and Notes

- Switchboard base: `33a5836496fa933dd6aae65ec71238d1b5ac9772`.
- Issue: #138.
- Branch: `feat/trusted-workload-catalog-dogfood`.
- Draft PR: #139.
- Initial target: `Nobodyworld/app-accounting-modular` PR #126.
- Observed target head: `613cf89396c41a0ee3c3aa5886a55c264a38daf0`.
- Observed quality entry point: `python -m src.tools.quality_gate`.

Ultimate workflow IDs belong in external PR evidence after the final head exists; do not create a self-referential evidence commit.

## Interfaces and Dependencies

Provide equivalent strict interfaces even if names change to fit repository conventions:

- immutable trusted repository/workload type;
- catalog iteration, lookup, repository/manifest compatibility, and canonical digest helpers;
- worker registration field for bounded logical repository names;
- persisted worker list with restart-safe compatibility;
- bounded repository-unavailable routing reason;
- authenticated catalog list/detail schemas and routes;
- repository-aware command-center readiness;
- `validate-accounting-modular@1` trusted fixed-argv manifest.

Use the standard library and current FastAPI, Pydantic, SQLAlchemy, pytest, and Playwright stack. Do not add a dependency unless it is necessary, pinned, audited, documented, and accepted within issue #138.
