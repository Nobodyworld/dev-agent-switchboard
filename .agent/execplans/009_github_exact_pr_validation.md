# Add exact GitHub pull-request validation

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

Primary implementation issue: #122. Parent epic: #111. The exact-SHA compact evidence foundation was merged through #114 / PR #120 at `dcb8e283f8445dd76f215a98023197d8ed5acab3`.

## Purpose / Big Picture

An authorized operator should be able to ask Switchboard to validate a GitHub pull request by repository and PR number rather than manually copying a commit SHA. Switchboard must resolve one immutable current head SHA, create a normal pending work order for `validate-switchboard@1`, preserve the existing explicit approval gate, execute through the trusted local worker, re-resolve the PR head before publication, and publish one bounded managed PR comment that is truthful for exactly the tested SHA.

The feature is successful when a mocked GitHub PR can be resolved into an exact-SHA work order, approved and executed through the existing control plane, and summarized back to a managed comment without exposing commands, secrets, full logs, environment dumps, absolute paths, response bodies, or local artifact locations. If the PR head changes before publication, the result must be recorded as stale and must never be presented as current success.

## Progress

- [x] Phase 1B exact-SHA compact evidence merged at `dcb8e283f8445dd76f215a98023197d8ed5acab3`.
- [x] Issue #122 rewritten with the locked first-slice product and security boundaries.
- [x] Canonical branch `feat/github-exact-pr-validation` created from the exact merged base.
- [x] Initial living ExecPlan added.
- [x] Inspect current execution service, API, configuration, database migration, CLI, and testing patterns.
- [x] Decide and document the first supported credential mode and minimum GitHub permissions.
- [x] Define strict versioned GitHub adapter request, resolved PR identity, publication, and reason-code contracts.
- [x] Recover and audit the interrupted local-only implementation without
  discarding or rewriting any preserved file.
- [x] Implement configured-host enforcement and bounded typed GitHub transport.
- [x] Persist idempotent adapter request/result identity linked to work order and run.
- [x] Add authenticated manual request surface.
- [x] Resolve an exact PR head and create a pending `validate-switchboard@1` work order.
- [x] Preserve explicit approval and fresh execution without #121.
- [x] Add managed bounded PR-comment rendering and update-in-place identity.
- [x] Re-resolve the PR head immediately before publication and fail stale results closed.
- [x] Add focused security, transport, schema, persistence, idempotency, stale-head, and publication tests.
- [x] Add a server-backed mocked-GitHub end-to-end proof.
- [x] Update operator, API, security, architecture, and integration documentation.
- [x] Run focused and complete local validation.
- [x] Push intentional implementation and focused CI-correction commits to
  update the existing draft PR #125.
- [x] Record final hosted Commitlint and complete CI evidence.

## Surprises & Discoveries

- Observation: the repository's established schema-upgrade path uses additive
  `Base.metadata.create_all()` startup behavior and startup compatibility tests;
  it does not run the historical Alembic revisions during application startup.
  A new focused adapter table therefore upgrades existing databases safely
  without runtime column DDL.
  Evidence: `server/api/lifecycle.py`,
  `server/tests/test_execution_startup.py`, and the existing separate execution
  tables in `server/models.py`.

- Observation: the adapter lifecycle cannot be represented safely by the
  current work-order or evidence records. Stable GitHub identity, deterministic
  request identity, managed-comment ownership, current/stale publication state,
  and retry timestamps have different mutation and retention semantics.
  Evidence: `ExecutionWorkOrder` contains immutable execution inputs and
  lifecycle fields, while `ExecutionRun.evidence_metadata` is strict worker
  evidence and intentionally excludes remote publication state.

- Observation: the shared Python 3.14 interpreter has an unrelated
  `opencv-python`/NumPy conflict. Initial validation recovered the isolated
  Python 3.11.14 venv at
  `C:\tmp\switchboard-github-exact-pr-validation-venv`; final validation uses
  the task-only standalone Python 3.11.14 installation recorded below so
  Windows worker children resolve the same tool environment.
  Evidence: shared `python -m pip check` reported the conflict; the isolated
  environment installed `server/requirements-dev.txt` and reports no broken
  requirements.

- Observation: activating the recovered venv still cannot influence the first
  executable search location of a Windows child launched as literal `python`.
  The venv launcher delegates to the Astral base process, whose executable
  directory contains another `python.exe`; Windows selects that before
  `PATH`. A task-only standalone CPython 3.11.14 installation under
  `C:\tmp\switchboard-github-exact-pr-validation-python311` keeps the parent,
  unchanged reviewed child command, and installed tools in one isolated
  application directory.
  Evidence: the activated venv rerun produced `2 passed, 2 failed`, both at
  Ruff; the standalone environment then produced `4 passed` for the complete
  server-backed worker file without changing worker interpreter selection or
  manifest argv.

- Observation: the first Windows server-backed worker baseline was launched
  without the isolated environment activated for the full parent process. The
  reviewed literal `python` therefore resolved an interpreter without Ruff and
  the validation stopped at that step. This is an environment setup condition,
  not evidence of a repository defect, and does not justify changing reviewed
  worker argv or interpreter selection.
  Evidence: the required server-backed baseline reached the exact-SHA worktree
  but failed the Ruff step with `No module named ruff`. Revalidation must run
  after activating the existing isolated Python 3.11 environment so its
  `Scripts` directory is present throughout the worker process tree.

- Observation: the interrupted implementation was preserved in exactly ten
  expected paths: three modified tracked files and seven untracked adapter/API
  files. Recovery preflight found no unrelated changes, a clean
  `git diff --check`, one owning worktree, local and remote head
  `4964f5a3d1fde424f4dd5d00f53910939a717b48`, and locked merge-base
  `dcb8e283f8445dd76f215a98023197d8ed5acab3`.
  Evidence: the 2026-07-24 recovery commands recorded in this plan's concrete
  workflow and the preservation comment on draft PR #125.

- Observation: the preserved adapter modules compile and import directly, but
  the API router cannot import because dependency construction is absent. The
  package initializer, router registration, startup/schema coverage, focused
  tests, server-backed proof, and documentation are also absent.
  Evidence: Python 3.11 `py_compile` succeeded for all ten paths; importing
  `server.api.routers.github_execution` failed only for the missing
  `GitHubAdapterServiceDependency`.

- Observation: the audit found defects that must be corrected before the draft
  can be treated as integrated: slots-based response conversion uses a missing
  `__dict__`; comment selection can choose an exact-marker copy before the
  persisted managed comment; deleted-head response handling is not explicit;
  GitHub settings do not normalize invalid ports into a bounded error; and
  write ambiguity/rate-limit classification needs stricter tests.
  Evidence: `server/github_adapter/schemas.py`,
  `server/github_adapter/service.py`, `server/github_adapter/transport.py`, and
  `server/settings.py`.

- Observation: a generic `worker_error:ValueError` did not truthfully
  distinguish an unavailable exact local commit from other preparation
  failures. A narrow `LocalCommitUnavailableError` now maps only the failed
  local `git cat-file` boundary to
  `requested_sha_not_available_locally`; it does not expose paths, fetch,
  substitute a SHA, or create compact evidence.
  Evidence: the mocked-GitHub server-backed acceptance resolves an absent fork
  SHA, approves it, runs the existing worker, persists that exact bounded
  failure with no evidence, and verifies the canonical repository is unchanged.

- Observation: the first complete pytest run exposed test isolation rather
  than a production defect. The new API service tests constructed a separate
  FastAPI application, which replaced the existing process-global
  rate-limit middleware pointer used by later legacy tests. Reusing the
  repository's single `server.app.app` fixture restored isolation; the
  relevant ordering regression produced `73 passed`, and the complete rerun
  produced `430 passed, 4 skipped`.
  Evidence: `server/tests/test_github_adapter_service.py` and the full
  2026-07-24 pytest transcript.

- Observation: Lychee's checked-in configuration writes its Markdown result
  to `lychee/out.md`, so a local output directory must exist before invoking
  the documented command. The generated report and cache are validation
  artifacts only and are removed before staging.
  Evidence: `lychee.toml` and the successful 2026-07-24 run summarized below.

- Observation: the first hosted implementation CI run found that the local
  pre-commit invocation occurred before the new adapter modules were staged.
  `--all-files` therefore checked only files already tracked by Git, while the
  Linux runner checked the newly committed modules and reported one
  `PLR0913`, four Ruff formatting changes, and one Black formatting change.
  The reported detect-secrets failure was partly hook-chain fallout and also
  identified two credential-redaction sentinels assigned to a variable named
  `secret`; no real or fixture credential was present. The service now accepts
  one typed dependency bundle, the pinned formatters have processed all
  tracked files, and the redaction sentinels use a non-credential identifier.
  Evidence: Commitlint run `30127902826` succeeded; CI run `30127902796`
  passed test, typecheck, security, links, and secrets-audit jobs but failed
  lint. The focused correction rerun produced `52 passed`, full Mypy remained
  clean across 172 files, Bandit passed, and every pre-commit hook passed.

## Decision Log

- Decision: implement a managed PR comment rather than the Checks API in the first slice.
  Rationale: comments require a smaller permission and persistence surface, are directly reviewable through the existing GitHub connector, and avoid falsely claiming check-run integration before installation permissions and lifecycle semantics are proven.
  Date/Author: 2026-07-23 / ChatGPT connector planning

- Decision: preserve the existing explicit Switchboard approval gate.
  Rationale: a GitHub PR number resolves identity only. Labels, comments, authorship, draft state, or other remote display data are not sufficient authorization to execute local work.
  Date/Author: 2026-07-23 / ChatGPT connector planning

- Decision: fresh execution must work without evidence reuse.
  Rationale: #122 establishes the high-value request-to-result loop. #121 is a later optimization and must not become a hidden prerequisite or broaden this implementation.
  Date/Author: 2026-07-23 / ChatGPT connector planning

- Decision: no webhook ingestion in the first slice.
  Rationale: a manual authenticated request flow proves immutable head resolution, idempotency, execution, stale-head handling, and publication without adding webhook signatures, replay protection, public ingress, or event-delivery ambiguity.
  Date/Author: 2026-07-23 / ChatGPT connector planning

- Decision: GitHub content is untrusted display data and never executable input.
  Rationale: titles, branch names, users, bodies, comments, workflow output, and returned URLs can contain attacker-controlled text. The adapter may render bounded escaped display fields but may execute only reviewed Switchboard manifest definitions.
  Date/Author: 2026-07-23 / ChatGPT connector planning

- Decision: support exactly one operator-configured fine-grained GitHub personal
  access token through `SWITCHBOARD_GITHUB_TOKEN`.
  `SWITCHBOARD_GITHUB_API_URL` defaults to exactly
  `https://api.github.com`, and `SWITCHBOARD_OPERATOR_ID` defaults to the
  bounded `local-operator` identity. The minimum documented repository
  permissions are **Metadata: read** and **Pull requests: read and write**.
  Rationale: this is the connector-resolved first-slice credential contract. It
  keeps credentials server-side and avoids a general provider or GitHub App
  installation abstraction.
  Date/Author: 2026-07-24 / Codex implementation

- Decision: expose the explicit synchronous authenticated flow
  `POST /api/execution/github/pull-requests/validate`,
  `GET /api/execution/github/requests/{request_id}`, and
  `POST /api/execution/github/requests/{request_id}/publish`.
  Rationale: callers provide only repository full name, PR number, and trusted
  manifest name/version. Resolution, digest binding, pending work-order
  creation, terminal evidence selection, head recheck, and publication remain
  server-owned. No scheduler, webhook, automatic polling, approval, or queueing
  is introduced.
  Date/Author: 2026-07-24 / Codex implementation

- Decision: add one focused `github_validation_requests` table linked to the
  normal execution work order and optional terminal run.
  Rationale: a unique deterministic idempotency key, stable GitHub
  repository/PR/head identity, managed-comment ID, current/stale publication
  state, bounded reasons, and retry timestamps cannot be added to execution
  evidence or work-order metadata without breaking their ownership and
  immutability boundaries. The table is additive under the established startup
  schema path.
  Date/Author: 2026-07-24 / Codex implementation

- Decision: use `httpx`, already pinned by the server, behind a fixed-route
  bounded GitHub transport.
  Rationale: the transport can enforce one configured HTTPS API base, disable
  redirect following, stream and bound response bytes before decoding, reject
  unknown/malformed response shapes, retry safe reads only, and keep
  authorization values and response bodies out of errors.
  Date/Author: 2026-07-24 / Codex implementation

- Decision: use
  `<!-- switchboard-validation:v1:<64-lowercase-hex-idempotency-hash> -->`
  as the exact managed-comment marker and persist the created comment ID.
  Rationale: the hash binds the configured GitHub host, stable repository and
  PR identity, exact tested SHA, and trusted manifest name/version/digest.
  Publication lists a bounded first page to recover the exact marker before a
  create, never retries comment creation blindly, and updates only the
  persisted managed identity or an exact-marker recovery.
  Date/Author: 2026-07-24 / Codex implementation

- Decision: the adapter resolves identity but never synchronizes source.
  Rationale: no Git fetch, remote mutation, ref write, or GitHub credential is
  added to the worker. The exact resolved PR head object must already exist in
  the operator-configured canonical repository. A missing object produces a
  bounded failed run reason, no success evidence, no SHA substitution, and no
  canonical repository mutation. Fork heads follow the same rule.
  Date/Author: 2026-07-24 / Codex implementation

## Outcomes & Retrospective

An interrupted local-only draft has been recovered and audited. It contains the
initial settings, one-table persistence model, transport, repository, renderer,
service, schemas, and API route definitions. The recovered draft is now wired
into the application, corrected for the audited defects, covered by mocked
transport/service/API/startup and real-worker acceptance tests, and documented.
The local implementation and required validation matrix are complete. The
adapter exposes the three authenticated manual endpoints, stores one narrow
request lifecycle record, creates an ordinary pending exact-SHA work order,
preserves explicit approval, uses fresh local execution, rechecks the head
immediately before publication, and creates or updates one bounded managed
comment. A moved head is retained as historical tested identity and published
as stale. Missing local commit objects fail with the requested SHA preserved,
no evidence, no fetch, no substitution, and no canonical-repository mutation.

All GitHub tests use mocked transports and no live token or GitHub network
access. Focused suites, full pytest, strict browser tests, configured coverage
thresholds, formatting, lint, typing, dependency checks, security checks,
secret scanning, and link validation pass. Four full-suite skips are existing
Windows filesystem/privilege cases; strict browser validation has zero skips.
The implementation and focused CI-correction commits are pushed only to the
canonical branch. Hosted Commitlint `30128491708` and CI `30128491658` both
succeeded, including all CI lint, typecheck, test, security, secrets-audit,
link, browser, and coverage jobs. Draft PR #125 remains open and unmerged;
final remote equality and cleanliness are verified at handoff.

## Context and Orientation

The current merged execution foundation lives primarily under:

- `server/execution/registry.py` — immutable trusted manifest definitions.
- `server/execution/evidence.py` — strict compact evidence and deterministic fingerprints.
- `server/execution/schemas.py` — authenticated execution request and response contracts.
- `server/execution/service.py` — work-order, run, lease, completion, and evidence lifecycle.
- `server/execution/repository.py` — persistence operations and concurrency boundaries.
- `server/api/routers/execution.py` — authenticated control-plane routes.
- `server/models.py` and migration/startup code — persisted records.
- `server/settings.py` and API/application configuration — operator-owned settings.
- `client/python/execution_worker/` — outbound worker; this issue should not add GitHub credentials or GitHub API behavior to the worker.
- `docs/API.md`, `docs/architecture/local-execution-broker.md`, and `docs/operations/local-worker.md` — current public contracts and trust boundaries.
- `server/tests/` and `client/python/tests/` — execution, API, persistence, security, and server-backed fixtures.

The adapter should live on the server/operator side. Work orders and workers must receive only resolved safe identity and the existing trusted manifest reference. GitHub credentials, HTTP response bodies, comment identifiers, and publication transport state must not enter worker payloads or compact evidence.

## Plan of Work

1. Inspect the current configuration, execution service, repository, migration, API, CLI, and test-fixture patterns. Record whether a new table is necessary or whether adapter identity can safely extend an existing record. Do not choose a migration merely for convenience.
2. Define strict versioned models for the operator request, resolved GitHub PR identity, adapter lifecycle, publication identity, and bounded reason codes. Reject unknown fields and executable-shaped or path-bearing values at the server boundary.
3. Add operator-owned GitHub configuration. Allow only one configured API host, one documented credential mode, bounded timeouts/retries, bounded response sizes, and fixed endpoint construction. Keep secrets out of `repr`, logs, work orders, workers, API responses, and persistence display fields.
4. Implement a typed transport for exactly the required repository, pull-request, comment-list, comment-create, and comment-update routes. Do not follow arbitrary URLs from GitHub content. Handle 404, deleted heads, rate limits, and transient failures with bounded reason codes.
5. Implement deterministic adapter request idempotency from resolved repository/PR/head/manifest identity. Repeated requests for the same exact head must not create uncontrolled duplicate work orders.
6. Add an authenticated manual API endpoint and/or CLI that accepts only repository full name, PR number, and trusted manifest reference. Resolve the remote identity server-side, enforce the existing repository allowlist, and create a normal pending work order that still requires explicit approval.
7. Link the adapter request to the resulting work order and terminal run. Fresh execution must use the existing `validate-switchboard@1` path unchanged.
8. Render one bounded managed comment with a constant machine-recognizable marker. Escape or normalize all remote display fields. Include exact tested SHA, manifest identity, terminal status/reason, parsed results when available, evidence fingerprint, fresh/reused provenance, current/stale decision, and the statement that full logs and artifact bytes remain local.
9. Immediately before publication, resolve the PR again. If the head moved, was deleted, or became unavailable, record stale state and do not publish current success for the new head. Updating the managed comment to a bounded stale result is permitted.
10. Add focused and server-backed tests using mocked GitHub transport only. Prove idempotency, approval preservation, stale-head behavior, no duplicate publication, no user-comment editing, configured-host enforcement, secret redaction, Markdown-marker resistance, and bounded output.
11. Update documentation with exact credential permissions, setup, API/CLI usage, failure modes, trust boundaries, and non-goals. Do not claim Checks API, webhooks, evidence reuse, workflow dispatch, or automatic approval.
12. Run the complete validation matrix, review the diff for secrets and scope, commit intentionally, push only the canonical branch, and keep the PR draft for connector review.

## Concrete Steps

Start by verifying the exact repository state:

```text
git fetch origin --prune
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git merge-base HEAD origin/main
git worktree list --porcelain
```

Expected starting identities:

```text
branch: feat/github-exact-pr-validation
HEAD: branch planning commit descending from dcb8e283f8445dd76f215a98023197d8ed5acab3
origin/main: dcb8e283f8445dd76f215a98023197d8ed5acab3
merge-base: dcb8e283f8445dd76f215a98023197d8ed5acab3
```

Stop before implementation if the branch is dirty unexpectedly, another worktree owns it, the remote branch differs materially, or the merge base is not the exact locked base.

Inspect before editing:

```text
python -m pytest -q -p no:cacheprovider server/tests/test_execution_contracts.py server/tests/test_execution_evidence.py
python -m pytest -q -p no:cacheprovider client/python/tests/test_execution_worker_server_smoke.py
```

During implementation, run focused tests for each contract and transport layer. At final validation run the candidate’s current protected commands, including pinned pre-commit, TODO validation, Ruff, Black, Mypy, full pytest, configured coverage thresholds, strict browser tests, Bandit, `pip-audit`, full-history Gitleaks, link validation, and `git diff --check`.

Automated tests must not require live GitHub credentials or external network access.

## Validation and Acceptance

Acceptance requires a server-backed mocked-GitHub scenario:

1. An authenticated operator submits an allowlisted repository and PR number.
2. The adapter resolves one stable repository/PR identity and exact 40-character head SHA.
3. Repeating the same request does not create duplicate uncontrolled work orders.
4. The normal pending work order is explicitly approved and executed through `validate-switchboard@1`.
5. The adapter reads compact terminal evidence without accessing full local logs.
6. The adapter re-resolves the PR head.
7. When unchanged, it creates or updates exactly one managed bounded comment for the exact tested SHA.
8. When changed, it records and publishes stale state and never reports current success for the new head.
9. The published payload contains no secrets, authorization values, response bodies, commands, argv, absolute paths, environment dumps, full logs, or local artifact locations.
10. The canonical repository and local worker security boundaries remain unchanged.

The complete local and hosted matrix must pass. The draft PR must include exact head SHA, focused/full results, final workflow IDs, credential mode and minimum permissions, and known limitations.

## Idempotence and Recovery

- Repeating an identical adapter request must return or reuse the same adapter identity rather than create duplicate work orders.
- Retrying safe GitHub reads may use bounded retry rules; comment creation/update must use persisted managed-comment identity and must not duplicate on ambiguous outcomes.
- A failed or rate-limited publication remains retryable without rerunning validation when the exact tested evidence and PR head are still current.
- A changed head creates a new request identity; do not mutate the old tested SHA into the new one.
- Database migrations, if necessary, must be restart-safe and tested from existing schemas.
- Never recover by exposing tokens, response bodies, full logs, or local paths.
- Do not reset, rebase, force-push, or discard unrelated local work. Stop and report material state drift.

## Artifacts and Notes

Record here during implementation:

- exact GitHub credential mode: one server/operator fine-grained PAT in
  `SWITCHBOARD_GITHUB_TOKEN`; minimum repository permissions are Metadata
  (read) and Pull requests (read and write);
- resolved request and publication schema examples with secrets removed;
- baseline focused execution/evidence command:
  `python -m pytest -q -p no:cacheprovider server/tests/test_execution_contracts.py server/tests/test_execution_evidence.py`
  produced `45 passed`;
- baseline worker smoke initially produced `2 passed, 1 failed` because the
  worker process tree did not retain the activated isolated environment and the
  reviewed `python` command could not import Ruff; no repository fix is
  justified for that baseline environment condition, and the smoke must be
  rerun with the environment activated;
- activated recovered-venv worker suite produced `2 passed, 2 failed`, with
  both validation cases stopping because Windows resolved the base interpreter
  without Ruff; the task-only standalone CPython 3.11.14 environment produced
  `4 passed` in `37.72s` without a worker/manifest interpreter change;
- focused mocked transport/configuration and adapter
  service/API/startup tests produced `48 passed` in `56.15s`;
- required execution/evidence baseline produced `45 passed` in `74.03s`;
- complete mocked-GitHub/server-backed worker tests produced `4 passed` in
  `37.72s` under the task-only standalone CPython 3.11.14 environment;
- the final combined adapter/startup/worker rerun after replacing
  credential-shaped test placeholders produced `52 passed` in `54.80s`;
- the focused post-hosted-lint correction rerun produced `52 passed` in
  `55.27s`; full Mypy, Bandit, and every pinned pre-commit hook also passed;
- mocked stale-head and idempotency proof includes current, moved, unavailable,
  stable-identity mismatch, ambiguous create recovery, copied-marker
  resistance, and rate-limit retry scenarios;
- `python -m pip check`: no broken requirements;
- pinned pre-commit: every configured hook passed;
- TODO policy: passed;
- Ruff: passed;
- Black: passed;
- Mypy: success with no issues in 172 source files;
- complete pytest: `430 passed, 4 skipped, 5 warnings` in `446.20s`;
- strict Playwright browser suite:
  `2 passed` in `22.74s`, with `SWITCHBOARD_STRICT_PLAYWRIGHT=1` and zero
  skips;
- configured coverage run:
  `430 passed, 4 skipped, 5 warnings` in `501.62s`, 91% aggregate coverage;
- coverage gate results:
  `contracts.py` 95.40% >= 85%,
  `interfaces.py` 94.17% >= 85%,
  `loader.py` 100% >= 85%,
  `runtime.py` 100% >= 85%,
  `task_metrics.py` 92.59% >= 85%,
  `plan_metrics.py` 95% >= 85%,
  `plan_latency.py` 87.76% >= 80%,
  `plan_snapshot.py` 100% >= 80%,
  `activity_feed.py` 100% >= 85%,
  `extensions/observability.py` 97.73% >= 80%,
  `diagnostics.py` 90.16% >= 80%,
  `health.py` 95.78% >= 85%,
  `activity.py` 94.83% >= 80%,
  `overview.py` 100% >= 85%,
  `task_service.py` 79.23% >= 75%, and
  `configuration_service.py` 91.30% >= 85%;
- Bandit: passed;
- `pip-audit`: no known vulnerabilities found;
- Gitleaks: scanned 219 commits / approximately 3.86 MB with no leaks;
- Lychee: 167 total links, 78 unique, 162 successful, five excluded, two
  redirects, zero timeouts, zero unknown links, and zero errors;
- `git diff --check`: passed before final staging;
- final implementation Commitlint `30128491708`: success;
- final implementation CI `30128491658`: success, including successful lint,
  typecheck, test, security, secrets audit, link check, strict browser, and
  coverage jobs;
- any transport, rate-limit, or installation limitations.

## Interfaces and Dependencies

The implementation should introduce only focused interfaces, expected to include equivalents of:

- a strict operator request model containing repository, PR number, and trusted manifest reference;
- a strict resolved PR identity containing configured host, stable repository/PR identities, exact head SHA, state, draft flag, and bounded display metadata;
- a deterministic adapter idempotency identity;
- a server-side GitHub transport with fixed route methods;
- an adapter service that resolves, creates the pending work order, reconciles terminal evidence, rechecks the head, and publishes;
- a bounded managed-comment renderer and marker;
- persisted adapter request/result linkage to work order and run;
- authenticated API and/or CLI entry point.

Do not add GitHub libraries or dependencies unless the standard HTTP stack cannot satisfy the typed bounded transport safely. Any new dependency requires a demonstrated need, pinning/audit review, and documentation.
