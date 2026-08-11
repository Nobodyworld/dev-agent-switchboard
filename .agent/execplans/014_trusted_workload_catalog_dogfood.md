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
- [x] Record baseline local validation before production edits.
- [x] Implement a strict trusted repository/workload catalog while preserving existing manifest digests.
- [x] Add `validate-accounting-modular@1` with fixed reviewed argv and bounded evidence.
- [x] Add bounded worker logical-repository availability and restart-safe persistence.
- [x] Make both routing policies, hard pins, assessment, and exact reuse repository-aware.
- [x] Add catalog/readiness APIs and repository-aware command-center onboarding.
- [x] Add focused catalog, migration, routing, adapter, worker, evidence, and browser regressions.
- [x] Complete a production-path synthetic fresh-then-reuse proof for the external workload contract.
- [x] Complete controlled local dogfood against the exact current head of `Nobodyworld/app-accounting-modular` PR #126, or record a precise environment blocker.
- [x] Update authoritative docs and the public-safe screenshot where needed.
- [x] Run the complete protected local matrix, cleanup, and public-hygiene audit.
- [x] Reconcile review `4901645651`, merge current `origin/main` normally, and preserve PR #141's commitlint and lifecycle fixes.
- [x] Replace the divergent readiness projection with the shared routing evaluator and add request-aware API/UI coverage.
- [x] Restore broad CI to Python 3.11 and isolate the truthful accounting acceptance in a guarded Python 3.12 job.
- [x] Complete the refreshed protected matrix for the review follow-up.
- [ ] Push focused commits, record ultimate-head hosted evidence externally, and keep PR #139 draft and unmerged.

## Surprises & Discoveries

- Observation: Planning review `4892665741`, PR checkpoint `5237014283`, and issue checkpoint `5237016607` were reconciled before editing; the existing branch and draft PR remained exact, open, draft, and unmerged at preflight.
  Evidence: local and remote branch head `dc33806e57edd8d0255b3f17c8379a482cf8ab31`; `origin/main` and merge base `33a5836496fa933dd6aae65ec71238d1b5ac9772`.

- Observation: The configured local Switchboard coordination endpoint was unavailable before editing, so no task state was invented or mirrored.
  Evidence: `http://127.0.0.1:8000/api/plan` did not accept the coordination request; Git and this living plan remain the authoritative local record.

- Observation: Review `4901645651` identified three connected correctness gaps: readiness ignored manifest capability constraints, broad CI was moved to Python 3.12 to accommodate one workload, and exact `.`/`..` repository segments crossed validation boundaries.
  Evidence: pre-follow-up PR head `9cd8c54e22740cbd1dbad2f9629e39ce24823293`; current `origin/main` `83f84a7ee07b4f5cdddfa7611242a529897fa842`; normal merge commit `2ba6d23970687067ae6c8888b06cd7751fb8e5ff`. The merge had no conflicts and incorporated the current `commitlint.config.js` and `server/api/lifecycle.py` fixes from PR #141.

- Observation: Repository readiness had become a second policy implementation based on the operator projection, so it could label a Python 3.11 accounting worker ready even though checkout rejected it.
  Evidence: the follow-up routes readiness, assessment, and checkout through `RoutingEvaluationRequest` and `evaluate_routing_candidate`; focused backend tests and strict Playwright prove the 3.11 mismatch and truthful 3.12 transition.

- Observation: The external target changed after planning: `Nobodyworld/app-accounting-modular` PR #126 is now merged rather than an open current PR.
  Evidence: final head `a7af5766a4e83a95c64a40bfdc606ee7b280cbf5`, base `445241b4514baa42feef0541b677233920540114`, merge commit `4266ea43ed40201388df82bb53f757df45afe204`, merged 2026-08-10 19:36:36Z. This blocks truthful current-PR dogfood and publication; the production-path synthetic real-worker proof remains required.

- Observation: The untouched focused baseline passed all repository tests: backend `117 passed`, worker `37 passed`, and strict Playwright `3 passed` with zero skips.
  Evidence: Python 3.14.0 baseline commands completed in 70.75s, 44.71s, and 29.87s respectively. Existing identities were `worker-smoke@1` digest `63e645f19d8c60ae442e1800aaecc1a18a719d53f22ba8e85ec62bf745ed55d1` and `validate-switchboard@1` digest `10e99418e4e6f0e9f4a6e95fb5b9a267dab4eeac4671cf58533c8b9afe1fed98`.

- Observation: The workstation-global Python 3.14 environment fails `pip check` on unrelated `opencv-python`/NumPy and Streamlit/Pillow version conflicts, while Python 3.13 reports no broken requirements but lacks `aiosqlite` for repository tests.
  Evidence: recorded before edits; no global environment was modified to mask the baseline condition.

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

- Observation: declared coverage files are produced in the disposable checkout, while retained evidence is a separate marker-owned tree.
  Evidence: the first real accounting run executed all eleven commands but initially could not finalize `coverage.xml` and `coverage.json`; `EvidenceStore.capture_declared_artifact()` now copies only reviewed regular contained artifacts under size bounds before hashing/finalization, and focused missing-file/regular-copy tests pass.

- Observation: Windows child-process resolution for the trusted fixed token `python` does not preserve a venv when the parent executable is a Python launcher, and the accounting contract truthfully requires Python 3.12+.
  Evidence: the real accounting acceptance remains truthful and is skipped only below Python 3.12; hosted quality and coverage stay on Python 3.11 while the dedicated `Accounting workload acceptance` job runs that one selector on Python 3.12 and rejects skips.

- Observation: invalid negative quota form state briefly issued readiness requests that FastAPI correctly rejected with 422, creating strict-browser console errors.
  Evidence: readiness now stays locally unavailable until the input is a non-negative safe integer; strict Playwright then passed `3 passed` with zero skips and zero unexpected console errors.

- Observation: the first hosted Python 3.11 `test` job failed after 516 passing tests because the production rate limiter retained the shared ASGI test-client bucket across pytest cases; fast hosted execution reached 120 requests inside the 60-second window while slower local execution aged entries out.
  Evidence: CI run `31487309953`, job `93765547262`, failed only `server/tests/test_leases.py::test_completion_with_and_without_active_lease` when a completion request returned 429. The autouse state fixture now reloads restored environment settings and resets every live in-process limiter before and after each test. A two-app regression plus the exact hosted pytest command passed locally: `621 passed, 5 skipped`.

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

- Decision: Treat merged target PR #126 as an exact target-state blocker and do not represent synthetic execution as current-PR dogfood.
  Rationale: A merged PR cannot truthfully demonstrate current/stale publication for an open target, and issue #138 explicitly forbids fabricated remote evidence or mutation of the external repository.
  Date/Author: 2026-08-10 / implementation

- Decision: Keep the catalog API executable-data-free and expose support status, documentation reference, allowed/default manifest identities, and non-mutating per-worker readiness only.
  Rationale: operators need onboarding and eligibility state, not argv, environment values, paths, or arbitrary capabilities.
  Date/Author: 2026-08-10 / implementation

- Decision: Preserve the target's Python 3.12+ constraint without changing the repository-wide quality and coverage baseline.
  Rationale: the real LocalWorker acceptance must execute under a truthful supported runtime, while unrelated suites should retain Python 3.11 coverage. A dedicated required job can enforce exactly one non-skipped accounting pass.
  Date/Author: 2026-08-11 / review follow-up

- Decision: Keep one pure eligibility evaluator and project its detailed reasons into a smaller operator-safe readiness vocabulary.
  Rationale: assessment, checkout, and readiness must agree on repository, pin, liveness, polling, status, capacity, manifest/request capabilities, network, and read-only posture. Profile, cost, and quota remain policy-specific to `cheapest_capable`.
  Date/Author: 2026-08-11 / review follow-up

- Decision: Reject exact `.` and `..` owner or repository segments through one central repository identity validator while preserving periods inside ordinary segments.
  Rationale: the prior broad syntax remains compatible, but path-special segments cannot cross catalog, execution, evidence, GitHub schema, or transport boundaries.
  Date/Author: 2026-08-11 / review follow-up

- Decision: Isolate rate-limit request buckets in the existing autouse test-state fixture rather than weakening production defaults or special-casing the failed lease test.
  Rationale: database and file state were already reset per case, and every application instance uses the same client identity in tests. Resetting all live limiter instances makes the suite deterministic while retaining dedicated rate-limit coverage and production behavior.
  Date/Author: 2026-08-11 / hosted CI follow-up

## Outcomes & Retrospective

The source-controlled catalog now contains Switchboard and modular accounting with canonical digest `3e8fe68e917d1afa5615e158f3ef69ac78193f356502c8e6fb071799edad5436`. Historical `worker-smoke@1` and `validate-switchboard@1` digests remain unchanged. The new `validate-accounting-modular@1` digest is `892f1269cdf2a6f4e0df4d86879e5dae980374d598faeadee77c2c32f33aa612`; its eleven fixed, shell-free steps bind three dependency inputs, read-only policy, Python 3.12+, bounded parsers, command logs, and retained coverage XML/JSON.

Workers now persist sorted logical repository identities only. The additive SQLite compatibility upgrade defaults prior rows to Switchboard, survives a second startup, and preserves valid values. Direct and GitHub creation reject unknown repositories and cross-repository manifest pairs before persistence. First-available, cheapest-capable, hard pins, assessment, checkout, and exact reuse exclude unmapped workers before route/capacity/quota/lease mutation.

The command center loads the bounded catalog, filters defaults, shows read-only readiness and logical worker availability, and retains approval/publication, keyboard, token, desktop, and 390-pixel safety. The 2026-08-10 public screenshot was recaptured from the offline synthetic UI acceptance fixture and contains no local identity or secret.

The real server-backed accounting acceptance used `ExecutionClient`, `LocalWorker`, `WorkerConfig`, `EvidenceStore`, mocked GitHub transport, file-backed SQLite, and a committed disposable canonical repository. The mapped worker executed 11 fresh steps; the cheaper unmapped worker could not claim. Retained ownership, result, logs, `coverage.xml`, and `coverage.json` were verified. A distinct second run reused after one worker-local verification with zero executed steps and preserved the source fingerprint. The mocked publications were explicitly invoked and resolved current then stale after a head move; before explicit publication the transport had zero comments. Overview/history reported one fresh success, one reused success, one deterministic execution avoided, 50% reuse, and two history rows. No lease, active capacity, disposable worktree, or canonical Git change remained. One captured proof produced fresh run `1`, reused run `2`, and source fingerprint `330a5f3aaec98c76f8bd92807369c42901def2a6b7fc8f4709b46b2429ed385c`.

Live current-PR dogfood was not performed because target PR #126 had already merged at exact head `a7af5766a4e83a95c64a40bfdc606ee7b280cbf5`; no external repository or publication was mutated. Docker and attended Edge workloads remain deferred as separate capability/threat profiles.

The review follow-up now evaluates repository readiness with the selected
manifest and routing inputs through the same pure path used by route assessment
and checkout. First-available remains profile-free; cheapest-capable retains
profile, cost, quota, and deterministic ranking. Readiness returns bounded safe
reasons and performs no persistence mutation. Repository identities reject exact
dot segments centrally while continuing to accept ordinary periods.

Refreshed review-follow-up validation passed on 2026-08-11: focused catalog,
routing, evidence, and transport coverage `149 passed`; complete non-UI pytest
`617 passed, 5 skipped`; strict Playwright `3 passed` with the JUnit guard
confirming zero skips; and the exact accounting selector `1 passed` with its
guard confirming exactly one test and no failures, errors, or skips. The
accounting proof executed 11 fresh steps and zero reused steps. Coverage remained
93% aggregate and all 16 configured module thresholds passed with the same
percentages recorded below. Pre-commit, TODO policy, Mypy (180 files), pinned
Bandit 1.8.6 under Python 3.13, pip-audit, Gitleaks (265 commits), Lychee, Node
syntax, workflow YAML, diff whitespace, and in-app browser interaction/visual QA
passed. The broad combined local pytest command exceeded its harness timeout
only because locally installed Chromium executes the UI module inline; the
repository's staged non-UI plus strict-UI shape completed cleanly.

The first hosted follow-up run exposed one speed-dependent shared rate-limit
bucket in the broad Python 3.11 job after 516 passes. After isolating limiter
state in the autouse fixture, the exact hosted pytest command completed locally
with `621 passed, 5 skipped, 344 warnings` in 7m41s, including all three UI
tests. Focused rate-limit and lease regressions passed `10 passed`. Ultimate-head
hosted evidence remains external to this non-self-referential plan.

Focused validation passed: dependency health clean; backend `127 passed`; worker/evidence `59 passed, 2` mutually exclusive OS skips; accounting acceptance separately `1 passed`; strict Playwright `3 passed`, zero skips. Complete pytest passed `604 passed, 5 skipped, 344 warnings`. Coverage passed at 93% aggregate and all 16 thresholds: contracts 95.40%, interfaces 94.17%, loader 100%, runtime 100%, task metrics 92.59%, plan metrics 95%, plan latency 87.76%, plan snapshot 100%, activity feed 100%, extension observability 97.73%, diagnostics 90.16%, health 97.59%, activity 94.83%, overview 100%, task service 90.71%, and configuration service 91.30%. Pre-commit, TODO policy, repository-pinned Ruff, Black, Mypy (180 files), pinned Bandit 1.8.6, pip-audit, Gitleaks (266 commits), and Lychee all passed. Generated reports, databases, caches, bytecode, Lychee state, and temporary environments were removed; the changed-file public-hygiene scan found no local worktree path, workstation identity, credential, private URL, or generated evidence. Commits, push, and hosted workflow evidence remain external delivery steps.

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
- Planning-time target head: `613cf89396c41a0ee3c3aa5886a55c264a38daf0`.
- Final merged target head re-resolved before editing: `a7af5766a4e83a95c64a40bfdc606ee7b280cbf5`.
- Target merge commit: `4266ea43ed40201388df82bb53f757df45afe204`.
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
