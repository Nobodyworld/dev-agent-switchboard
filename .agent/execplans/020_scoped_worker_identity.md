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
- [x] Record exact current route/client call graph before implementation edits (2026-09-14).
- [x] Implement persisted worker credential verifier state and additive/idempotent startup compatibility.
- [x] Implement administrator-only issue/rotate/revoke surfaces with one-time plaintext return.
- [x] Implement worker-auth principal/dependencies and narrow route authorization.
- [x] Split the worker HTTP client from the broad administrator/operator execution client.
- [x] Migrate manual local worker to process-private `SWITCHBOARD_WORKER_TOKEN`.
- [x] Migrate owned operator validation lifecycle so the child worker never receives `SWITCHBOARD_ADMIN_TOKEN`.
- [x] Add rotation/revocation, impersonation, ownership-loss, leakage, migration, and lifecycle regressions.
- [x] Update operations/security docs, moving status, and this living plan.
- [x] Run complete local validation.
- [ ] Verify exact-head hosted workflows after normal publication.
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

Implemented the scoped credential contract in one isolated slice worktree while preserving the primary checkout and all retained state. The administrator explicitly issues a server-generated secret; the database retains one verifier record per worker. The worker uses nine dedicated routes and loses authority on subsequent requests after rotation/revocation. Real process tests prove that both transitions cancel an already-started subprocess, retain failure evidence, leave the authoritative run unfinished, and stop further checkout. Final validation and hosted publication evidence are recorded below as they complete. The PR remains draft and unmerged; independent review and any later ready/merge decision remain separate.

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

## Execution route and client authority inventory (before implementation)

Preflight on 2026-09-14 matched local/remote prepared head `4099ad9eab97b14acd8f293a5eadd8791b61fdd3` and main `ce0cb9e9fdfadf8e31a751789c795743330e8624`. The owner confirmed PR #160 remains open/draft/unmerged. Bounded Git status excluded exactly the three preserved cache roots, confirmed no tracked entries there and no other dirt. One detached slice worktree preserves the primary and all four retained worktrees. First source correction removes the extra final newline; unchanged-head CI is not rerun.

The matrix classifies the accepted mode with a configured administrator token. All 42 existing execution routes use the administrator dependency; dedicated worker routes are added separately. Explicit per-route dependencies and an enumerated regression guard this boundary. The pre-existing unconfigured demo mode makes the administrator dependency optional; it is not an accepted credentialed worker/operator lifecycle. Credential management refuses that mode, and worker-shaped credentials are rejected outside the dedicated worker routes even there.

| Existing route | Handler | Current authority | Final authority |
|---|---|---|---|
| `GET /api/execution/catalog` | `get_trusted_catalog` | Administrator | Administrator |
| `GET /api/execution/catalog-readiness` | `get_catalog_readiness` | Administrator | Administrator |
| `GET /api/execution/trusted-repositories` | `list_trusted_repositories` | Administrator | Administrator |
| `GET /api/execution/trusted-repositories/{owner}/{repository}` | `get_trusted_repository_detail` | Administrator | Administrator |
| `GET /api/execution/trusted-repositories/{owner}/{repository}/readiness` | `get_named_trusted_repository_readiness` | Administrator | Administrator |
| `GET /api/execution/catalog/{repository_full_name:path}/readiness` | `get_trusted_repository_readiness` | Administrator | Administrator |
| `GET /api/execution/operator/overview` | `get_operator_overview` | Administrator | Administrator |
| `GET /api/execution/operator/history` | `list_operator_history` | Administrator | Administrator |
| `GET /api/execution/workers` | `list_execution_workers` | Administrator | Administrator |
| `GET /api/execution/manifests` | `list_manifests` | Administrator | Administrator |
| `GET /api/execution/manifests/{name}/{version}` | `get_manifest` | Administrator | Administrator |
| `POST /api/execution/work-orders` | `create_work_order` | Administrator | Administrator |
| `GET /api/execution/work-orders` | `list_work_orders` | Administrator | Administrator |
| `GET /api/execution/work-orders/{work_order_id}` | `get_work_order` | Administrator | Administrator |
| `POST /api/execution/work-orders/{work_order_id}/approve` | `approve_work_order` | Administrator | Administrator |
| `POST /api/execution/work-orders/{work_order_id}/queue` | `queue_work_order` | Administrator | Administrator |
| `POST /api/execution/work-orders/{work_order_id}/reject` | `reject_work_order` | Administrator | Administrator |
| `POST /api/execution/work-orders/{work_order_id}/cancel` | `cancel_work_order` | Administrator | Administrator |
| `POST /api/execution/work-orders/{work_order_id}/expire` | `expire_work_order` | Administrator | Administrator |
| `POST /api/execution/work-orders/{work_order_id}/requeue` | `requeue_stale_work_order` | Administrator | Administrator |
| `GET /api/execution/work-orders/{work_order_id}/route-assessment` | `assess_work_order_route` | Administrator | Administrator |
| `GET /api/execution/work-orders/{work_order_id}/route` | `get_work_order_route` | Administrator | Administrator |
| `POST /api/execution/routing-profiles` | `create_routing_profile` | Administrator | Administrator |
| `GET /api/execution/routing-profiles` | `list_routing_profiles` | Administrator | Administrator |
| `GET /api/execution/routing-profiles/{worker_id}` | `get_routing_profile` | Administrator | Administrator |
| `PUT /api/execution/routing-profiles/{worker_id}` | `replace_routing_profile` | Administrator | Administrator |
| `POST /api/execution/routing-profiles/{worker_id}/quota-reset` | `reset_routing_quota` | Administrator | Administrator |
| `POST /api/execution/workers` | `register_worker` | Administrator | Administrator |
| `POST /api/execution/workers/{worker_id}/heartbeat` | `heartbeat_worker` | Administrator | Administrator |
| `POST /api/execution/checkout` | `checkout_execution_work` | Administrator | Administrator |
| `GET /api/execution/runs` | `list_runs` | Administrator | Administrator |
| `GET /api/execution/runs/{run_id}` | `get_run` | Administrator | Administrator |
| `GET /api/execution/runs/{run_id}/route` | `get_run_route` | Administrator | Administrator |
| `GET /api/execution/runs/{run_id}/evidence` | `get_run_evidence` | Administrator | Administrator |
| `POST /api/execution/runs/{run_id}/reuse-candidate` | `resolve_reuse_candidate` | Administrator | Administrator |
| `POST /api/execution/runs/{run_id}/heartbeat` | `heartbeat_run` | Administrator | Administrator |
| `POST /api/execution/runs/{run_id}/complete` | `complete_run` | Administrator | Administrator |
| `POST /api/execution/leases/expire` | `expire_stale_execution_leases` | Administrator | Administrator |
| `GET /api/execution/github/requests` | `list_github_validation_requests` | Administrator | Administrator |
| `POST /api/execution/github/pull-requests/validate` | `request_pull_request_validation` | Administrator | Administrator |
| `GET /api/execution/github/requests/{request_id}` | `get_github_validation_request` | Administrator | Administrator |
| `POST /api/execution/github/requests/{request_id}/publish` | `publish_github_validation_request` | Administrator | Administrator |

| Existing client method | Current authority | Final use |
|---|---|---|
| `__init__` | Administrator credential | Transport/resource lifecycle; no independent route authority |
| `__enter__` | Administrator credential | Transport/resource lifecycle; no independent route authority |
| `__exit__` | Administrator credential | Transport/resource lifecycle; no independent route authority |
| `close` | Administrator credential | Transport/resource lifecycle; no independent route authority |
| `list_manifests` | Administrator credential | Administrator/operator only |
| `get_manifest` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `health_ready` | Administrator credential | Administrator/operator only |
| `list_workers` | Administrator credential | Administrator/operator only |
| `repository_readiness` | Administrator credential | Administrator/operator only |
| `create_work_order` | Administrator credential | Administrator/operator only |
| `approve_work_order` | Administrator credential | Administrator/operator only |
| `queue_work_order` | Administrator credential | Administrator/operator only |
| `assess_work_order_route` | Administrator credential | Administrator/operator only |
| `get_work_order_route` | Administrator credential | Administrator/operator only |
| `list_runs` | Administrator credential | Administrator/operator only |
| `get_run_evidence` | Administrator credential | Administrator/operator only |
| `register_worker` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `heartbeat_worker` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `checkout` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `get_work_order` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `get_run` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `heartbeat_run` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `resolve_reuse_candidate` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `complete_run` | Administrator credential | Worker lifecycle; separate worker client uses dedicated worker routes |
| `_request_json` | Administrator credential | Transport/resource lifecycle; no independent route authority |
| `_request` | Administrator credential | Transport/resource lifecycle; no independent route authority |

The outbound `LocalWorker` and `_RunMonitor` use eight of the nine reviewed worker client methods; `get_run` is retained as an explicitly scoped owned-run read: `register_worker`, `heartbeat_worker`, `checkout`, `get_manifest`, `get_work_order`, `get_run`, `heartbeat_run`, `resolve_reuse_candidate`, `complete_run`. Each will use the equivalent dedicated `/api/execution/worker` route. Manifest reads additionally carry the assigned run ID and must match its immutable manifest; work-order reads require the current assigned run to belong to the principal; run reads/writes require the authoritative run worker ID. Path/body/query worker substitutions are rejected. Registration and checkout require the exact credential worker ID. Operator `health_ready` calls `/health/ready`, an existing separately classified public readiness probe; it is absent from the worker client. Private transport helpers are not authority grants.

Credential management adds administrator-only `POST /api/execution/worker-credentials/{worker_id}/issue`, `POST .../rotate`, `POST .../revoke`, and `GET /api/execution/worker-credentials/{worker_id}`. Provisioning reserves an offline logical worker identity if needed, with no advertised repositories/capabilities until its authenticated registration. One credential row per worker bounds history, with random credential ID, SHA-256 verifier and timestamps. Rotation replaces the row atomically; no overlapping credentials or automatic write retries.

### Implementation decisions and validation in progress (2026-09-14)

- Existing 42 execution routes retain explicit administrator dependencies in the configured mode classified above. Nine new worker routes and four credential-management routes make 55 execution routes in total. The matrix regression also compares the route inventory against generated OpenAPI so a new unclassified execution route fails the gate.
- `WorkerExecutionClient` has exactly nine lifecycle methods plus resource `close`; it shares only transport and worker operations with the broad administrator subtype. It never inherits administrator methods. `LocalWorker` requires this narrow interface. Authentication rejection latches the worker client closed and cancels active execution without completion.
- Dedicated routes reject identity substitution; manifest reads require the owned run ID. Credential management requires a configured administrator and expected credential ID for rotation/revocation. One new table is additive and bounds state to one row per worker; no previous table is changed.
- The operator lifecycle preserves the existing report/progress schema and marker checks. Revocation failure makes the outcome fail with a bounded reason. Successful shutdown records revocation in the database before stopping the owned processes.
- Focused validation is underway. Initial fixture and cancellation-ordering defects were corrected; no pre-correction result is acceptance evidence. The current pinned FastAPI uses included-router objects, so matrix validation inspects concrete routers and cross-checks OpenAPI instead of assuming application routes are already flattened.

- Focused execution reached 125 passes, including scoped auth, actual long-process 401/403 cancellation, and all three non-Switchboard workload acceptances, before three real operator scenario teardowns exposed an unclosed SQLite connection in the newly added assertion. The connection is now explicitly closed; the partially cleaned failed synthetic roots remain preserved. This was a test resource-ownership defect, not a worker authority failure. The corrected focused matrix must pass before the full suite.
- Pinned tool checks now pass: Ruff/format, both Windows and Linux-target Mypy (212 source files), Bandit, server/client dependency audits, full-history Gitleaks (353 commits), workload catalog (four entries), TODO checks, and Lychee (195 successes, five configured exclusions, no errors). Final candidate checks remain required after any further source changes.


### Completed focused proof and compatibility correction

- The corrected focused run passed 153 tests with two explicit Windows symlink skips. It includes all four real IPv4/IPv6 fresh-only/fresh-then-exact-reuse operator scenarios, marker/approval/progress/readiness compatibility, containment and process/port cleanup.
- The final credential module passed all 19 cases, including deliberate rotation and revocation after an actual worker subprocess starts. The real server then rejects the old token; the process stops, the source checkout is removed only after containment proof, local failure evidence remains, and the authoritative run stays `running` with no finish timestamp. No completion or replacement checkout is fabricated.
- Prior-schema migration now starts with a real existing worker row. Its identity, display name, capabilities and repository registry survive startup, issuance, and two repeated startups; the same verifier still authenticates. The credential table has exactly the six reviewed columns.
- The strict browser gate exposed a legacy-demo compatibility regression: the UI sends a synthetic administrator sentinel when no administrator is configured. Restored the existing unconfigured-demo administrator behavior while the separate middleware still denies worker-shaped credentials outside worker routes. Credential issuance always requires a configured administrator. A regression covers both cases. Strict Playwright then passed all four cases with zero skips.
- The timing-sensitive cancellation fixture discovers its fixed host capabilities before the timed operation. Its existing five-second cancellation assertion remains unchanged; real lifecycle and capability tests still perform their own discovery.
- Python 3.13 and the catalog-pinned Node 24.12.0/pnpm 10.18.1 let all non-Switchboard workload acceptances execute locally. These are repository-owned synthetic acceptance fixtures, not live external-repository execution or production proof.
- Factory coverage passed 25 tests: reviewed profile validation 240/240 lines (100%) and catalog readiness 62/67 lines (92.54%), both above the unchanged 90% thresholds. Windows and Linux-target Mypy pass over 212 files.

### Final worker and management route additions

| Route | Authority and ownership |
|---|---|
| `POST /api/execution/worker/workers` | Worker principal; matching body worker ID |
| `POST /api/execution/worker/workers/{worker_id}/heartbeat` | Worker principal; matching path worker ID |
| `POST /api/execution/worker/checkout` | Worker principal; matching body worker ID |
| `GET /api/execution/worker/work-orders/{work_order_id}` | Worker principal owns latest assigned run |
| `GET /api/execution/worker/runs/{run_id}` | Worker principal owns authoritative run |
| `GET /api/execution/worker/manifests/{name}/{version}?run_id=...` | Owned run and exact assigned manifest |
| `POST /api/execution/worker/runs/{run_id}/heartbeat` | Matching body worker ID and authoritative run/lease ownership |
| `POST /api/execution/worker/runs/{run_id}/reuse-candidate` | Matching body worker ID and authoritative run/lease ownership |
| `POST /api/execution/worker/runs/{run_id}/complete` | Matching body worker ID and authoritative run/lease ownership |
| `POST /api/execution/worker-credentials/{worker_id}/issue` | Configured administrator; one-time secret return |
| `POST /api/execution/worker-credentials/{worker_id}/rotate` | Configured administrator; atomic expected-ID transition |
| `POST /api/execution/worker-credentials/{worker_id}/revoke` | Configured administrator; idempotent expected-ID revocation |
| `GET /api/execution/worker-credentials/{worker_id}` | Configured administrator; non-secret metadata only |

No public execution route is added. Malformed/unknown/revoked credentials, duplicate authentication headers, mixed administrator/worker headers and duplicate/substituted query IDs fail closed. Cross-worker registration, checkout, run reads, heartbeat, reuse lookup, completion and manifest/work-order reads are covered. One primary-key row bounds credential history; rotation and stale revocation use compare-and-set identity rather than retries. Authentication is uncached; requests authorized before revocation are not retrospectively undone.

### Changed file inventory

- `.agent/execplans/020_scoped_worker_identity.md`
- `README.md`
- `SECURITY.md`
- `client/python/execution_operator/lifecycle.py`
- `client/python/execution_operator/models.py`
- `client/python/execution_operator/processes.py`
- `client/python/execution_worker/__init__.py`
- `client/python/execution_worker/client.py`
- `client/python/execution_worker/config.py`
- `client/python/execution_worker/runner.py`
- `client/python/execution_worker/worker.py`
- `client/python/tests/test_execution_operator.py`
- `client/python/tests/test_execution_operator_progress.py`
- `client/python/tests/test_execution_worker_capabilities.py`
- `client/python/tests/test_execution_worker_checkout_race.py`
- `client/python/tests/test_execution_worker_config_models.py`
- `client/python/tests/test_execution_worker_foundations.py`
- `client/python/tests/test_execution_worker_profile_contract.py`
- `client/python/tests/test_execution_worker_reuse.py`
- `client/python/tests/test_execution_worker_runner.py`
- `client/python/tests/test_execution_worker_runtime.py`
- `client/python/tests/test_execution_worker_server_smoke.py`
- `client/python/tests/test_execution_worker_strict_containment.py`
- `client/python/tests/test_execution_worker_strict_work_order.py`
- `client/python/tests/test_scoped_worker_client.py`
- `docs/API.md`
- `docs/architecture/local-execution-broker.md`
- `docs/message-schema.md`
- `docs/operations/local-worker.md`
- `docs/operations/operator-validation-lifecycle.md`
- `docs/operations/worker-credentials.md`
- `docs/reports/status.md`
- `scripts/local_worker.py`
- `server/api/__init__.py`
- `server/api/dependencies.py`
- `server/api/routers/execution.py`
- `server/api/routers/github_execution.py`
- `server/api/routers/worker_credentials.py`
- `server/api/routers/worker_execution.py`
- `server/execution/credentials.py`
- `server/execution/operator_projection.py`
- `server/execution/text_policy.py`
- `server/models.py`
- `server/tests/test_worker_credentials.py`


### Local validation ledger (2026-09-14)

| Gate | Result |
|---|---|
| Final scoped credential/client regressions | PASS: 24 passed, zero skips |
| Operator/readiness/progress/security regression bundle | PASS: 153 passed, two unavailable Windows symlink skips |
| Standalone full pytest | PASS: 1,009 passed, 16 skips; ran before the two additional active-process transition cases |
| `python scripts/dev.py verify` | PASS: 1,011 passed, 16 skips; Ruff, Windows Mypy, Bandit, all 20 module thresholds and installed-environment dependency audit passed |
| Additional CI coverage thresholds | PASS: interfaces and task service; all 22 CI module gates satisfied |
| Measured aggregate coverage | PASS: 90.09% (2,773/3,078 measured statements) |
| Strict Playwright | PASS: four passed, zero skips; also enabled in the verify invocation |
| Full pre-commit | PASS: ten hooks passed; Prettier skipped because the repository hook regex matched no files |
| Ruff check/format and Black | PASS |
| Windows / Linux-target Mypy | PASS: 212 source files each |
| Bandit | PASS: repository server scope; no manager scan errors |
| Dependency audits | PASS: server requirements, declared client requirements and installed validation environment; no known vulnerabilities |
| detect-secrets | PASS with the existing baseline; no baseline regeneration |
| Gitleaks | PASS: staged candidate; historical full-history scan covered 353 commits; final committed history must be rescanned before push |
| Lychee 0.24.2 | PASS: 195 successes, five configured exclusions, two redirects, zero errors |
| Workload catalog | PASS: four reviewed entries; no catalog changes |
| Workload factory/readiness coverage | PASS: 25 tests; 100% and 92.54% against unchanged 90% gates |
| Workload acceptances | PASS: all eight server-backed smoke/validation/reuse/GitHub-mock cases, including Accounting, Zscripts and Industry Resilience fixtures |
| Windows containment/cleanup | PASS: all applicable cases, including nine real junction cases and real IPv4/IPv6 process/port lifecycle proof |
| Actions/configuration | PASS: three workflows, 25 full-SHA action references, bounded job timeouts, read-only workflow contents permissions, checkout credentials not persisted, YAML/TOML syntax/duplicate-key checks |
| TODO annotations / diff whitespace / public-path hygiene | PASS |

The 16 full-suite skips are seven symlink tests unavailable under the current Windows privilege, five POSIX-only tests, three Linux-only containment tests, and one explicitly opt-in full Switchboard lifecycle acceptance. No browser or non-Switchboard workload acceptance was skipped. The real synthetic operator scenarios ran on both IPv4 and IPv6 in both lifecycle modes. No native Linux process execution is claimed by Linux-target Mypy; hosted Linux tests remain a separate gate.

Gitleaks classified the literal malformed-token fixture as a generic API key. The negative case now truncates a freshly generated token; the administrator-negative case reads the already configured synthetic fixture header. No scanner exception or baseline change was added. The final 24-case security/client run passed after this test-only correction; production code was unchanged from the complete verify run.

Validation files remain external to tracked evidence. The three earlier partially cleaned synthetic test roots remain preserved following the SQLite assertion connection failure. No historical runtime, branch, stash, worktree, or primary cache root was cleaned. Primary source state and all retained worktree heads remain unchanged.


The existing optional commit-message hook invocation fails because its pinned `conventional-pre-commit` version does not support the configured `--config` option. The same pinned validator passed with strict parsing and the exact eleven types in `conventional.yaml`; the normal `pre-commit --all-files` gate remains passing. No hook/configuration change, hook bypass flag, scanner suppression, or Git stash change is part of this slice. Hosted Commitlint remains a separate required check. Ruff also removed the now-unused test-only S105 suppression after the generated malformed-token fixture replaced the literal.

### Hosted validation correction (2026-09-15)

The first implementation commit `2da9019c3f4b147e56a65cc9f9bd98e01b73b416` passed the recorded Windows validation and was pushed normally. Hosted Commitlint and all three workload-acceptance jobs passed. CI passed lint, typecheck, security, secrets, links and Accounting acceptance, but its test job stopped at 117 passes, four skips and the first real IPv4 operator lifecycle failure (`loopback_port_not_released`). Dependent coverage and browser jobs were skipped, so that hosted run is not accepted.

A focused reproduction in the existing Ubuntu runtime proved the defect. Issuance reserves an offline identity with an empty repository list; the administrator worker-summary output required at least one repository. Polling before registration therefore returned HTTP 500. The server closed those failed connections, leaving server-side TCP TIME_WAIT entries which the unchanged exclusive-bind release check correctly rejected. The output summary now permits the empty provisioned state; authenticated registration still requires at least one reviewed repository. A new regression checks visibility, offline/unavailable state, no advertised authority, rejection of empty registration, and successful registration of the same identity. Real IPv4/IPv6 lifecycle cases also reject server tracebacks. No shutdown ordering, port probe, timeout, readiness, cleanup, or approval boundary is weakened. Corrected focused and complete validation remains required before the next normal push.

### Corrected candidate validation (2026-09-15)

- Native Linux focused proof: 31 passed, zero skipped. All four real IPv4/IPv6 fresh-only and fresh-then-exact-reuse scenarios passed with empty server-port socket tables at the unchanged exclusive-bind check. The two bound-but-not-listening rejection cases passed. Issuance/rotation/revocation, prior-schema/repeated startup, the full route/client boundary and both real active-process credential-loss cases passed.
- Windows focused security/operator/readiness/progress proof: 168 passed, four skipped (three unavailable symlink cases and the explicitly opt-in full Switchboard lifecycle).
- Complete `python scripts/dev.py verify`: 1,012 passed, 16 skipped, 348 warnings in 1,000.54 seconds. Strict Playwright ran all four browser cases with zero skips; all eight server-backed workload cases and nine real Windows junction cases passed. All 20 verify coverage gates and both additional CI module gates passed. Informational measured aggregate coverage is 89.96% (2,769/3,078 statements); no threshold changed. The installed dependency audit found no known vulnerabilities.
- Both Windows and Linux-target Mypy passed over 212 source files. Ruff check/format, Black, Bandit, TODO checks and the unchanged four-entry workload catalog passed. All ten applicable pre-commit hooks passed without modifying source; the existing Prettier regex matched no files. Staged Gitleaks and detect-secrets passed. Lychee passed 195 checks with five configured exclusions, two redirects and zero errors.
- The original complete declared-dependency audits, workload factory coverage and Action/config checks remain applicable: this correction changes one output list constraint, focused assertions and documentation; dependency declarations, factory logic and workflows are unchanged. Complete pytest was rerun on the corrected source as part of verify. Original failed Linux traces and corrected XML/log evidence are retained externally; all historical and failed runtimes remain preserved.
- The accepted authority matrix explicitly assumes a configured administrator token. Documentation now calls out the preserved optional administrator guard in legacy unconfigured demo mode, where credential management refuses operation. No worker credential is accepted outside the worker allowlist in either mode.

Normal correction publication and its exact-head hosted checks are next. The first implementation head's failed CI is historical and must not be retried or represented as passing. Independent connector review and owner ready/merge authorization remain outstanding; this implementation task preserves draft/unmerged state.
