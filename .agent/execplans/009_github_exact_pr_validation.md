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
- [ ] Inspect current execution service, API, configuration, database migration, CLI, and testing patterns.
- [ ] Decide and document the first supported credential mode and minimum GitHub permissions.
- [ ] Define strict versioned GitHub adapter request, resolved PR identity, publication, and reason-code contracts.
- [ ] Implement configured-host enforcement and bounded typed GitHub transport.
- [ ] Persist idempotent adapter request/result identity linked to work order and run.
- [ ] Add authenticated manual request surface.
- [ ] Resolve an exact PR head and create a pending `validate-switchboard@1` work order.
- [ ] Preserve explicit approval and fresh execution without #121.
- [ ] Add managed bounded PR-comment rendering and update-in-place identity.
- [ ] Re-resolve the PR head immediately before publication and fail stale results closed.
- [ ] Add focused security, transport, schema, persistence, idempotency, stale-head, and publication tests.
- [ ] Add a server-backed mocked-GitHub end-to-end proof.
- [ ] Update operator, API, security, architecture, and integration documentation.
- [ ] Run focused and complete local validation.
- [ ] Push intentional commits and open or update one draft PR.
- [ ] Record final hosted Commitlint and complete CI evidence.

## Surprises & Discoveries

- Observation: none recorded yet.
  Evidence: implementation inspection has not begun.

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

## Outcomes & Retrospective

Implementation has not started. At completion, summarize the delivered operator workflow, exact permissions, persistence model, stale-head behavior, managed-comment format, local and hosted validation, limitations, and any deferred work.

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

- exact GitHub credential mode and minimum repository permissions;
- resolved request and publication schema examples with secrets removed;
- focused test commands and counts;
- mocked stale-head and idempotency proof;
- complete local validation results;
- final Commitlint and CI run identifiers;
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
