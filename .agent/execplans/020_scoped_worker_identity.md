# Add scoped worker identity and revocation

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md` and `PROJECT_RULESET.md`.

## Purpose / Big Picture

Replace the temporary Phase-1 authentication arrangement in which an outbound local worker carries the same administrator credential as the operator control plane. After this slice, a worker should possess only a credential bound to its own logical `worker_id`, use only the narrowly reviewed worker lifecycle API, and lose that authority immediately after administrator rotation or revocation. Administrator/operator actions remain separately protected.

The user-visible proof is straightforward: an operator deliberately issues a worker credential, starts that worker with process-private `SWITCHBOARD_WORKER_TOKEN`, sees the worker register/poll/heartbeat/execute/complete normally, then can rotate or revoke the credential and observe fail-closed worker behavior without granting the worker work-order approval, routing, GitHub publication, or other administrator authority.

This remains `PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY`. It is not an OS sandbox, public identity provider, MCP security layer, or production authentication system.

## Progress

- [x] Issue #159 accepted as the active successor after #157 / PR #158.
- [x] PR #158 squash-merged as `ce0cb9e9fdfadf8e31a751789c795743330e8624`; resulting-main CI and Workload acceptance passed.
- [x] Canonical branch `feat/scoped-worker-identity` created from exact merged main.
- [x] Initial source/auth boundary inspected and implementation plan created.
- [ ] Record exact current route/client call graph before implementation edits.
- [ ] Implement persisted worker credential verifier state and additive/idempotent startup compatibility.
- [ ] Implement administrator-only issue/rotate/revoke surfaces with one-time plaintext return.
- [ ] Implement worker-auth principal/dependencies and narrow route authorization.
- [ ] Split the worker HTTP client from the broad administrator/operator execution client.
- [ ] Migrate manual local worker to process-private `SWITCHBOARD_WORKER_TOKEN`.
- [ ] Migrate owned operator validation lifecycle so the child worker never receives `SWITCHBOARD_ADMIN_TOKEN`.
- [ ] Add rotation/revocation, impersonation, ownership-loss, leakage, migration, and lifecycle regressions.
- [ ] Update operations/security docs, moving status, and this living plan.
- [ ] Run complete local validation and exact-head hosted workflows.
- [ ] Connector review complete with no unresolved blocker.
- [ ] Owner separately authorizes ready transition and merge.

## Surprises & Discoveries

- Observation: the entire execution router is currently protected by router-wide `require_admin_token`, so worker and operator authority are not distinguishable at the HTTP authorization layer.
  Evidence: `server/api/routers/execution.py` and `server/api/dependencies.py`.

- Observation: `WorkerConfig.from_mapping()` reads `SWITCHBOARD_ADMIN_TOKEN`, stores it only in a repr-hidden process object, and `ExecutionClient` sends it as a bearer token. The process-only handling is useful and should be preserved, but the authority is too broad.
  Evidence: `client/python/execution_worker/config.py` and `client/python/execution_worker/client.py`.

- Observation: `ExecutionClient` currently contains both operator methods such as work-order creation/approval/queueing and worker methods such as registration, checkout, heartbeat, reuse resolution, and completion. A worker-scoped secret must not merely be passed into this broad client because that would make privilege separation dependent on caller discipline.
  Evidence: `client/python/execution_worker/client.py`.

- Observation: `ExecutionWorker` already provides the durable logical worker identity and the execution repository/service already enforce run/lease ownership. Credential state should bind to that identity and reuse those ownership rules rather than creating a second worker registry.
  Evidence: `server/models.py`, `server/execution/repository.py`, and `server/execution/service.py`.

## Decision Log

- Decision: keep administrator authentication and worker authentication as distinct credential types and distinct dependency paths.
  Rationale: accepting a worker token through the existing router-wide administrator dependency would not reduce authority.
  Date/Author: 2026-09-08 / ChatGPT

- Decision: introduce a narrow worker HTTP client instead of placing a scoped worker token into the existing broad `ExecutionClient` surface.
  Rationale: the type/API surface should make it impossible for normal worker code to call create/approve/queue/routing/GitHub/operator methods with its credential.
  Date/Author: 2026-09-08 / ChatGPT

- Decision: use an opaque, server-generated high-entropy secret with a non-secret random credential identifier and persist only a one-way verifier plus bounded lifecycle metadata.
  Rationale: the server needs indexed lookup and constant-time verification without storing recoverable plaintext. High-entropy generated secrets do not require password-style human entropy assumptions.
  Date/Author: 2026-09-08 / ChatGPT

- Decision: allow at most one active worker credential per logical worker in this slice; rotation atomically invalidates the previous credential.
  Rationale: this gives simple, auditable revocation semantics and avoids overlapping-secret ambiguity. Any future grace-period policy requires a separate accepted contract.
  Date/Author: 2026-09-08 / ChatGPT

- Decision: use `SWITCHBOARD_WORKER_TOKEN` as the process-private manual-worker input and remove `SWITCHBOARD_ADMIN_TOKEN` from the accepted worker process path by definition of done.
  Rationale: it preserves the current environment-only secret pattern while making the authority boundary visible and testable.
  Date/Author: 2026-09-08 / ChatGPT

- Decision: the owned validation lifecycle may use its administrator authority to issue a runtime-scoped worker credential after server health and before child-worker launch, pass only that worker token to the worker process, and revoke it during owned shutdown when ownership remains proven.
  Rationale: the lifecycle owns a fresh isolated server/database runtime and should not require a second source-controlled secret while still ensuring its child worker never receives administrator authority.
  Date/Author: 2026-09-08 / ChatGPT

## Outcomes & Retrospective

Pending implementation. Record the final exact credential contract, route allowlist, migration result, worker/lifecycle behavior, validation totals, explicit skips, and any deferred security limitations here before review completion.

## Context and Orientation

Authoritative starting base is merged `main` at `ce0cb9e9fdfadf8e31a751789c795743330e8624`.

Key files and responsibilities:

- `server/api/dependencies.py` — current administrator token dependency; add worker-principal authentication without weakening admin behavior.
- `server/api/routers/execution.py` — current execution routes and router-wide admin dependency; classify every route as administrator-only, worker-only, or deliberately public/read-only.
- `server/models.py` — durable `ExecutionWorker` and execution models; add minimal credential verifier state using additive schema rules.
- `server/execution/repository.py` — persistence and transactional worker/run ownership operations.
- `server/execution/service.py` — execution domain operations; keep ownership authorization close to authoritative state.
- `client/python/execution_worker/config.py` — immutable local worker configuration; migrate secret source to `SWITCHBOARD_WORKER_TOKEN`.
- `client/python/execution_worker/client.py` — currently broad authenticated API client; retain operator/admin behavior where required and introduce a narrow worker client/interface.
- `client/python/execution_worker/worker.py` — actual outbound worker call graph that defines the minimum credential authority.
- `scripts/local_worker.py` — manual worker entry point.
- `client/python/execution_operator/` and `scripts/dev.py` — owned lifecycle, readiness, reporting, and operator surfaces that must preserve admin authority while launching the child worker with worker-only authority.
- `server/tests/`, `client/python/tests/`, and `tests/` — security, route, migration, worker, lifecycle, CLI, and leakage regressions.

Current worker operations must be inventoried from `LocalWorker` and its monitor rather than guessed. Likely required categories are own registration/refresh, own heartbeat, checkout, safe manifest metadata for assigned work, owned work-order/run reads, owned run heartbeat, reuse-candidate resolution, and owned completion. The implementation must prove the final list.

## Plan of Work

### 1. Lock the route/authority matrix

Before changing code, enumerate every `/api/execution` route and every `ExecutionClient` method. Classify each as:

- administrator/operator only;
- worker only;
- deliberately unauthenticated safe metadata, if any.

Do not leave a route implicitly authorized by router-wide inheritance. Add tests that enumerate or otherwise guard the security-sensitive matrix so future endpoints cannot accidentally default to worker authority.

### 2. Add minimal credential persistence

Add an additive credential record bound to one `ExecutionWorker.worker_id`. The recommended closed record contains only:

- random non-secret credential identifier;
- worker ID;
- one-way secret verifier;
- created/rotated/revoked timestamps as needed;
- active/revoked state or equivalent invariant.

Generate the plaintext secret with Python `secrets` using at least 256 bits of randomness. Use a closed token format containing a random public credential ID plus the secret component so lookup does not require scanning all records. Hash the secret with a standard cryptographic digest suitable for high-entropy opaque tokens and compare verifiers with `hmac.compare_digest` or an equivalent constant-time primitive.

Never persist plaintext, a reversible encrypted form, the Authorization header, or a token-derived value usable as authentication by itself. Bound credential counts and public projections. Prove startup from the previously supported schema and repeated startup.

### 3. Add administrator provisioning, rotation, and revocation

Use the existing administrator dependency for explicit management operations. Do not accept caller-authored secret bytes.

Provide typed bounded operations to:

- issue the first credential for an exact worker ID;
- rotate the credential atomically, returning the new plaintext once and invalidating the old credential;
- revoke the credential idempotently without generating a replacement;
- inspect only safe metadata such as worker ID, credential ID/fingerprint, state, and timestamps.

A one-time plaintext response must be excluded from logs, normal list/detail projections, reports, metrics, GitHub evidence, and error messages.

### 4. Add worker principal authentication and route authorization

Create a worker-auth dependency that parses one unambiguous bearer credential form, resolves its credential ID, verifies the secret, rejects revoked/unknown/malformed credentials, and returns a bounded authenticated principal containing only the logical worker identity needed for authorization.

Worker routes must compare authenticated identity with all path/body/query identity and authoritative run ownership. Reject cross-worker registration, heartbeat, checkout substitution, run reads, run heartbeat, reuse resolution, and completion.

Do not make the new dependency an alternate path through `require_admin_token`. Administrator-only routes must continue to require administrator authority.

### 5. Split worker and operator clients

Keep the administrator/operator client surface for lifecycle orchestration. Introduce a worker-only client/interface that exposes only the reviewed worker operations and always authenticates with the worker credential.

`LocalWorker` and `_RunMonitor` must depend only on the worker client. They must have no method to create, approve, queue, publish, route, or administer work.

On 401/403 or explicit credential-revoked responses, fail closed: stop taking new assignments, do not retry ambiguous writes indefinitely, cancel/preserve/clean an active owned execution through existing containment rules as far as authoritative ownership allows, and never fabricate completion.

### 6. Migrate manual worker and owned lifecycle

Manual `scripts.local_worker` configuration continues to exclude secrets from JSON. `WorkerConfig.from_mapping()` reads `SWITCHBOARD_WORKER_TOKEN`, not `SWITCHBOARD_ADMIN_TOKEN`, for the accepted path.

For the owned validation lifecycle:

1. run existing exact preflight;
2. start the owned server with administrator authority held only by the operator process/server environment;
3. issue a worker-scoped credential for the configured worker ID through the administrator client;
4. launch the worker with only the worker secret in its environment;
5. preserve current fresh/reuse approvals, evidence verification, progress, reports, and cleanup;
6. during owned shutdown, revoke the runtime credential only while marker/server ownership remains proven; failure to revoke is reported truthfully and must not authorize unsafe cleanup.

No credential value enters lifecycle JSON/human reports, progress events, process records, argv, or persisted runtime markers.

### 7. Validate security and compatibility

Add focused tests for:

- one-time issuance and no plaintext persistence;
- wrong/malformed/unknown/revoked credentials;
- rotation invalidating the old credential atomically;
- idempotent repeated revocation;
- another worker ID in path/body/query;
- another worker's work order/run/lease;
- attempts by worker token to create/approve/queue work, alter routing, or call other administrator surfaces;
- administrator paths remaining compatible;
- manual worker full lifecycle using only worker token;
- credential revocation during active execution and cleanup behavior;
- owned operator lifecycle on IPv4/IPv6 with child worker lacking the administrator token;
- fresh and exact-reuse compatibility;
- token absence from configs, logs, exceptions, reports, telemetry, metrics labels, database projections, and GitHub-safe output;
- previous-schema startup and repeated startup;
- existing readiness/progress and stored-report compatibility.

Then run complete repository validation without reducing any threshold: full pytest, `python scripts/dev.py verify`, strict Playwright, pre-commit, Ruff/format, Mypy, Bandit, dependency audit, detect-secrets/Gitleaks, link checks, workload catalog/acceptances, coverage gates, Action pinning/configuration checks, and the applicable Windows containment/junction/cancellation/process/port regressions.

## Concrete Steps

1. Verify the local repository identity and existing worktrees before creating a #159 worktree.
2. Fetch/fast-forward normally so remote `feat/scoped-worker-identity` is exactly the expected prepared head; stop on divergence or unknown dirty state.
3. Record the route/client authority matrix in this ExecPlan before implementation.
4. Implement in coherent layers: persistence -> auth principal -> routes -> clients -> worker -> lifecycle -> docs/tests.
5. Run focused security tests after each layer, then full validation only on the final coherent candidate.
6. Update this plan, issue #159, and draft PR evidence with exact final SHA and truthful local limitations.
7. Push normally. Do not rebase, force-push, merge, release, deploy, or clean preserved historical state.

## Validation and Acceptance

Acceptance requires all conditions in issue #159 plus:

- the worker process has no administrator credential in the accepted manual or owned-lifecycle path;
- a worker credential cannot exercise any operator/admin action even if it manually crafts the HTTP request;
- cross-worker identity substitution is rejected at both authentication/route and authoritative ownership boundaries;
- rotation/revocation changes authority immediately for subsequent requests without server restart;
- old plaintext credentials cannot be recovered from the database or any normal artifact;
- lifecycle and worker cleanup remain truthful after credential loss;
- exact-SHA, immutable manifest, explicit approval, evidence reuse, readiness/progress, and developer-preview boundaries remain intact;
- complete local and hosted validation passes at one exact final branch head.

## Idempotence and Recovery

- Credential issuance is deliberate and non-idempotent; callers must never automatically retry an ambiguous issuance/rotation response.
- Revocation is deliberately idempotent.
- Rotation is one atomic state transition: either the old credential remains authoritative or the new credential does, never both because of a partial commit.
- Startup schema compatibility is additive and repeated-start safe.
- Unknown authentication/persistence state fails closed rather than repairing credentials automatically.
- Preserve failed local runtimes and uncertain credential-loss cases for diagnosis; do not rewrite historical execution evidence.
- Do not reset, clean, stash, force-remove worktrees, or delete branches/runtimes/evidence as recovery shortcuts.

## Artifacts and Notes

Repository-safe evidence may contain logical worker IDs, non-secret credential IDs/fingerprints, bounded states/reason codes, timestamps, exact code SHA, and test counts. It must never contain plaintext worker/admin credentials, Authorization headers, private paths, environment dumps, or machine identity.

Historical #146/#149 evidence, retained failed/successful runtimes, existing branches/stashes, the #157 worktree/evidence until separately reconciled, and `security-deferral-wip` remain preserved.

## Interfaces and Dependencies

Expected interfaces may evolve during implementation, but preserve these architectural properties:

```python
@dataclass(frozen=True)
class WorkerPrincipal:
    worker_id: str
    credential_id: str

class WorkerExecutionClient:
    def register_worker(...) -> ...: ...
    def heartbeat_worker(...) -> ...: ...
    def checkout(...) -> ...: ...
    def get_manifest(...) -> ...: ...
    def get_work_order(...) -> ...: ...
    def get_run(...) -> ...: ...
    def heartbeat_run(...) -> ...: ...
    def resolve_reuse_candidate(...) -> ...: ...
    def complete_run(...) -> ...: ...
```

The worker client must not expose administrator work-order creation/approval/queueing, routing/profile mutation, GitHub publication, credential administration, or other operator authority.

Use only Python standard-library cryptographic randomness/comparison primitives unless existing project dependencies already provide a clearly superior reviewed primitive; do not add an authentication framework merely for this slice.