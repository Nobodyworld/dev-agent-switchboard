# API Reference

Switchboard exposes REST, health, observability, and WebSocket endpoints for agents and operators.
Use this page as the concise endpoint index; use [ai-interface.md](ai-interface.md) for payload examples and integration notes.

## Endpoint Table

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/agents` | `POST` | Register or idempotently confirm an agent identifier. |
| `/api/tasks` | `GET` | List tasks with dependency metadata; filter via `status`. |
| `/api/tasks` | `POST` | Create a task and optional dependency edges. |
| `/api/tasks/{id}` | `PUT`, `PATCH` | Update title, description, status, priority, or dependency edges. |
| `/api/tasks/{id}` | `DELETE` | Delete a task and refresh plan version if a record was removed. |
| `/api/tasks/checkout` | `POST` | Lease the next available task; failures include a `reason`. |
| `/api/tasks/{id}/heartbeat` | `POST` | Extend the active lease for the agent that checked out the task. |
| `/api/tasks/{id}/complete` | `POST` | Mark a task complete and store optional notes. |
| `/api/tasks/{id}/abandon` | `POST` | Release the lease without completion. |
| `/api/tasks/analytics` | `GET` | Return aggregated task analytics including ready and blocked counts. |
| `/api/execution/manifests` | `GET` | List trusted, server-controlled manifest identities and non-executable metadata. |
| `/api/execution/manifests/{name}/{version}` | `GET` | Read one immutable trusted manifest snapshot. |
| `/api/execution/work-orders` | `GET`, `POST` | List or create separately persisted work orders. Creation accepts only a manifest identity and safe policy metadata. |
| `/api/execution/work-orders/{id}` | `GET` | Read a work order and its lifecycle timestamps. |
| `/api/execution/work-orders/{id}/approve` | `POST` | Explicitly approve an allowlisted, read-only work order; it queues by default. |
| `/api/execution/work-orders/{id}/queue` | `POST` | Move an already approved work order into the worker-visible queue. |
| `/api/execution/work-orders/{id}/reject` | `POST` | Reject a pending work order. |
| `/api/execution/work-orders/{id}/cancel` | `POST` | Cancel a work order and release any active execution lease safely. |
| `/api/execution/work-orders/{id}/expire` | `POST` | Expire an unassigned approved or queued work order. |
| `/api/execution/work-orders/{id}/requeue` | `POST` | Requeue only an assigned/running order whose active lease is stale. |
| `/api/execution/work-orders/{id}/route-assessment` | `GET` | Assess the current bounded local-worker route for a queued work order without reserving capacity or quota and without refreshing worker polls. |
| `/api/execution/work-orders/{id}/route` | `GET` | Read compact persisted route provenance after assignment. |
| `/api/execution/routing-profiles` | `GET`, `POST` | List or create privileged operator-owned local-worker cost, quota, and priority profiles. |
| `/api/execution/routing-profiles/{worker_id}` | `GET`, `PUT` | Read or revision-protected replace one worker routing profile. |
| `/api/execution/routing-profiles/{worker_id}/quota-reset` | `POST` | Apply an explicit monotonic, revision-protected quota replacement. |
| `/api/execution/workers` | `GET`, `POST` | Read a bounded, redacted operator worker/profile projection or register/refresh a read-only worker capability declaration. |
| `/api/execution/workers/{worker_id}/heartbeat` | `POST` | Refresh a registered worker heartbeat and availability state. |
| `/api/execution/checkout` | `POST` | Atomically assign one capability-compatible queued work order to one worker. |
| `/api/execution/runs` | `GET` | List historical execution attempts; filter with `work_order_id`. |
| `/api/execution/runs/{id}` | `GET` | Read a bounded execution-run record. |
| `/api/execution/runs/{id}/route` | `GET` | Read compact persisted route provenance for one run. |
| `/api/execution/runs/{id}/evidence` | `GET` | Read strict, versioned compact evidence for a completed run; full logs remain worker-local. |
| `/api/execution/runs/{id}/heartbeat` | `POST` | Refresh a lease owned by the named worker and mark first execution start. |
| `/api/execution/runs/{id}/reuse-candidate` | `POST` | Resolve one server-selected exact candidate for the live lease owner after validating the worker-derived reuse identity. |
| `/api/execution/runs/{id}/complete` | `POST` | Record `succeeded`, `failed`, `timed_out`, or `cancelled` after ownership validation. |
| `/api/execution/leases/expire` | `POST` | Timeout stale runs, release worker capacity, and safely requeue their work orders. |
| `/api/execution/github/pull-requests/validate` | `POST` | Resolve an allowlisted GitHub PR to one exact head and create or return one normal pending work order. |
| `/api/execution/github/requests` | `GET` | List a bounded, stably ordered adapter projection with repository, lifecycle, reuse, and publication filters. |
| `/api/execution/github/requests/{request_id}` | `GET` | Return bounded adapter identity and execution/publication lifecycle. |
| `/api/execution/github/requests/{request_id}/publish` | `POST` | Recheck the PR head and synchronously create or update one bounded managed comment as current or stale. |
| `/api/execution/operator/overview` | `GET` | Return database-derived request, run, reuse, publication, avoided-work, and worker counts for a bounded day window. |
| `/api/execution/operator/history` | `GET` | Return bounded, paginated, newest-first request/work-order/latest-run history with redacted route and evidence fields. |
| `/api/plan` | `GET` | Return current plan snapshot used by agents and dashboard. |
| `/api/execplans/index` | `GET` | Return ExecPlan registry index in JSON (default) or YAML based on query/header negotiation. |
| `/health/live` | `GET` | Liveness probe returning process and probe observations. |
| `/health/ready` | `GET` | Readiness probe validating database and storage access. Returns HTTP 503 on failure. |
| `/health` | `GET` | Plaintext liveness heartbeat (`OK`). |
| `/api/health` | `GET` | Combined liveness and readiness envelope. Requires admin token when configured and returns HTTP 503 when readiness fails. |
| `/api/observability/overview` | `GET` | Aggregated observability overview for operators. Requires admin token when configured. |
| `/api/observability/telemetry` | `GET` | Logging, metrics, tracing, runtime metadata, and observability notes. Requires admin token when configured. |
| `/api/observability/metrics` | `GET` | Prometheus analytics catalog and latest sample metadata. |
| `/api/observability/health` | `GET` | Aggregated observability health view. Requires admin token when configured. |
| `/api/observability/audit-feed` | `GET` | Rolling in-memory audit feed from the builtin activity extension. Requires admin token when configured. |
| `/api/settings` | `GET` | Lease and rate-limit configuration used by the CLI and agents. |
| `/api/configuration` | `GET` | Consolidated configuration snapshot for operators. |
| `/api/diagnostics` | `GET` | Runtime metadata, package versions, feature toggles, and system state. |
| `/api/system-state` | `GET`, `PUT` | Inspect or toggle maintenance mode. `PUT` requires the admin token when `SWITCHBOARD_ADMIN_TOKEN` is set. |
| `/api/files/{path}` | `PUT` | Upload a live file served under `/live/<path>`. Protected by admin token when configured and bounded by size limits. |
| `/live/{path}` | `GET` | Fetch the current rendered live file content. |
| `/ws/plan` | `GET` (WebSocket) | Stream plan snapshots and version updates for dashboard and agent sync. |

## Operational Notes

- `SWITCHBOARD_ADMIN_TOKEN` protects privileged mutations such as maintenance changes and live-file uploads when configured.
- `SWITCHBOARD_MAX_LIVE_FILE_BYTES` bounds upload size for `/api/files/{path}`.
- Checkout, heartbeat, completion, and abandon semantics are covered by automated lease and concurrency tests under [server/tests](../server/tests/).

## Execution Control Plane (Phase 1A)

The `/api/execution/...` surface is separate from the legacy task DAG. In
particular, `/api/tasks/checkout` continues to lease high-level coordination
tasks and does not create an execution run; `/api/execution/checkout` uses its
own work-order, worker, run, and active-lease records.

All execution routes currently reuse `SWITCHBOARD_ADMIN_TOKEN` when it is
configured, including worker registration, checkout, heartbeat, and completion.
This is a deliberate Phase 1 credential limitation, not a worker identity
system. A scoped worker credential belongs to the later worker work.

Creation is deny-by-default: approval requires an allowlisted repository, an
exact 40-character SHA, an immutable trusted manifest identity/digest, explicit
approval, read-only repository policy, and an eligible worker. Request payloads
are strict and recursively reject executable-shaped keys in caller-controlled
metadata, so callers cannot submit a command string, argv array, shell,
script, executable path, or manifest digest at any nesting depth.

Expected request errors are explicit: missing credentials return `401`, missing
records return `404`, invalid lifecycle/ownership/approval conflicts return
`409`, and malformed or forbidden request fields return FastAPI validation
responses (`422`). A normal empty checkout returns `200` with a machine-readable
reason instead of treating no available work as a server failure.

Work-order creation also accepts a strict `routing_policy`:
`first_available` (the default) or `cheapest_capable`. Existing callers that
omit it keep the original capability-aware first-poller behavior and do not
need a routing profile. `cheapest_capable` considers only trusted outbound
local workers with a valid enabled operator-owned profile, fresh heartbeat,
fresh checkout poll, online capacity, matching manifest and work-order
capabilities, matching network posture, read-only repository capability,
sufficient integer quota, and an estimated integer cost no greater than
`maximum_cost_units` when supplied. Legacy floating-point `cost_ceiling`
remains accepted and stored for compatibility but never controls the new
route. Cost units are abstract operator comparison units, not dollars,
credits, spend, or measured savings.

Eligible workers are ranked deterministically by lowest
`estimated_cost_units_per_run`, highest quota headroom after the prospective
reservation, lowest active-load ratio (integer cross multiplication), lowest
operator `routing_priority`, and finally lexical worker ID. An explicit
`preferred_executor` is a hard pin to a known worker. It overrides ranking but
never approval, liveness, polling, status, capacity, capability, network,
read-only, cost, quota, or profile-enabled checks, and it never falls back to a
different worker when unavailable. An unknown hard pin submitted through the
GitHub validation route returns bounded `404 preferred_executor_not_found`; the
request transaction is rolled back before either an adapter request or work
order exists.

Every checkout by a known authenticated worker records only that requester's
`last_checkout_poll_at` using server time. Poll freshness and heartbeat
freshness are separate. A heartbeating worker that stops pulling ages out of
`cheapest_capable` candidacy; `first_available` compatibility is unchanged.
The successful checkout transaction conditionally reserves worker capacity
and quota, claims the queued order, and creates the run and lease together.
The first valid run heartbeat consumes reserved quota exactly once. A
pre-start cancellation or stale lease releases it exactly once; after start,
success, failure, timeout, cancellation, lease loss, and requeue do not refund
consumed quota. Profile replacement and quota reset require an exact revision
and fail closed while a reservation is active.

Normal work-order and run responses expose only bounded route provenance:
routing schema/policy, selected worker ID and profile revision, estimated cost,
required/reserved quota, reservation state, eligible count, pin flag, bounded
reason, and decision timestamp. They do not expose candidate lists, complete
profiles, capabilities, commands, argv, logs, credentials, environment dumps,
local roots, or private network details. This routing slice never dispatches a
paid coding agent or contacts an AI provider, billing service, or external
rate-limit API.

The outbound worker, rather than an API route, resolves reviewed executable
definitions and validates detached exact-SHA worktrees. The evidence endpoint
returns only strict bounded identities, summaries, relative artifact references,
SHA-256 hashes, retention timestamps, cleanup outcomes, and a deterministic
fingerprint. It returns `404` when the run or evidence is absent and `500` when
persisted evidence is malformed. Full logs, absolute paths, tokens, arbitrary
environment values, and artifact bytes are never returned.

Work-order creation accepts an optional `reuse_policy`: `never` (the default),
`allow_exact`, or `require_exact`. Callers cannot select a source run, worker,
fingerprint, artifact, or local path. For an opted-in assigned run, the worker
derives a versioned identity from the exact repository SHA, manifest
name/version/digest, current environment fingerprint, sorted dependency-lock
hashes, execution policy, and result contract. The live lease owner submits
that identity to `/api/execution/runs/{id}/reuse-candidate`; the server returns
only a bounded exact candidate or an unavailable reason.

Database metadata is never sufficient for reuse. The selected source worker
must locally reverify its marker-bound result and every declared artifact's
containment, ownership, retention, regular-file type, size, SHA-256, and
before/after stability. `allow_exact` falls back to one fresh execution under
the same live lease when proof fails. `require_exact` never runs validation and
finishes non-successfully when verified evidence is unavailable. A successful
reuse produces a distinct run with `reuse_decision`, bounded `reuse_reason`,
`reuse_identity`/hash, `reused_from_run_id`, and
`source_evidence_fingerprint`. Source bytes remain worker-local and their
retention is not changed.

## GitHub exact-PR adapter

The manual outbound adapter reuses `SWITCHBOARD_ADMIN_TOKEN` authentication.
Its create request accepts `repository_full_name`, `pull_request_number`, a
trusted manifest `name`/`version`, and optional strict `reuse_policy`,
`routing_policy`, `maximum_cost_units`, `required_quota_units`, and
`preferred_executor` fields. Defaults preserve the original `never` plus
`first_available` behavior. Stable GitHub identities, exact head SHA, base
provenance, manifest digest, work-order identity, terminal evidence, comment
identity, and publication state are server-owned. Unknown or executable-shaped
fields still return `422`.

An identical authenticated actor + stable PR + exact head + trusted manifest +
complete execution-policy request returns the same adapter and work-order
identities. Every accepted execution-policy field participates in the new
idempotency identity. An all-default request also recognizes the exact legacy
pre-command-center identity, so an existing default request is returned without
mutation or duplication; a non-default request never falls back to that legacy
identity. Policy remains authoritative on the linked work order rather than on
adapter-owned schema columns. A new head, credential actor, or material policy
creates a distinct request. The work order remains `pending_approval` until the
normal explicit approval route is called.

The operator projections accept bounded pagination (`limit` at most `100`,
`offset` at most `10000`) and the overview accepts a day window at most `365`.
History has stable newest-first ordering and joins only the latest run per
request. It never returns commands, argv, logs, environment dumps, local paths,
credentials, candidate lists, or complete worker capabilities. Avoided-work
counts include successful reused runs only; reference seconds come from each
linked successful source run's persisted start/finish interval, and comparison
units come from the reused run's persisted route estimate. Missing values are
excluded rather than guessed.

The command center combines the exact request status with existing bounded
`GET /api/execution/work-orders/{id}/route-assessment` and
`GET /api/execution/runs/{id}` reads. The former supplies a non-mutating queued
candidate decision; the latter supplies persisted route/quota provenance,
timestamps, cleanup, reuse source run/fingerprint, and compact evidence after a
run exists. The browser never requests full logs, commands, argv, environment
values, local paths, or unbounded candidate data.

Publication requires terminal compact evidence and re-resolves the PR
immediately before its managed comment is written. A moved or unavailable head
is published as stale without changing the historical tested SHA. Responses
and comments exclude credentials, remote response bodies, commands, full logs,
environment values, local paths, and artifact locations.

Every comment update is preceded by an authoritative fixed-route read that
verifies ID, configured actor, exact repository/PR association, API origin, and
first-line marker. Ambiguous create recovery uses a validated bounded
newest-page window. A database-backed publication lease permits one remote
writer per adapter request; concurrent callers receive bounded
`github_publication_in_progress` status without writing remotely.

See
[GitHub exact pull-request validation](operations/github-exact-pr-validation.md)
for credential permissions, marker recovery, local commit availability, and
transport limits.

See [Validation command center](operations/validation-command-center.md) for
the browser workflow and projection semantics.

## Related Docs

- [ai-interface.md](ai-interface.md)
- [message-schema.md](message-schema.md)
- [failure-modes.md](failure-modes.md)
- [observability.md](observability.md)
