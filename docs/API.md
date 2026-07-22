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
| `/api/execution/workers` | `POST` | Register or refresh a read-only worker capability declaration. |
| `/api/execution/workers/{worker_id}/heartbeat` | `POST` | Refresh a registered worker heartbeat and availability state. |
| `/api/execution/checkout` | `POST` | Atomically assign one capability-compatible queued work order to one worker. |
| `/api/execution/runs` | `GET` | List historical execution attempts; filter with `work_order_id`. |
| `/api/execution/runs/{id}` | `GET` | Read a bounded execution-run record. |
| `/api/execution/runs/{id}/evidence` | `GET` | Read strict, versioned compact evidence for a completed run; full logs remain worker-local. |
| `/api/execution/runs/{id}/heartbeat` | `POST` | Refresh a lease owned by the named worker and mark first execution start. |
| `/api/execution/runs/{id}/complete` | `POST` | Record `succeeded`, `failed`, `timed_out`, or `cancelled` after ownership validation. |
| `/api/execution/leases/expire` | `POST` | Timeout stale runs, release worker capacity, and safely requeue their work orders. |
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

The outbound worker, rather than an API route, resolves reviewed executable
definitions and validates detached exact-SHA worktrees. The evidence endpoint
returns only strict bounded identities, summaries, relative artifact references,
SHA-256 hashes, retention timestamps, cleanup outcomes, and a deterministic
fingerprint. It returns `404` when the run or evidence is absent and `500` when
persisted evidence is malformed. Full logs, absolute paths, tokens, arbitrary
environment values, and artifact bytes are never returned.

## Related Docs

- [ai-interface.md](ai-interface.md)
- [message-schema.md](message-schema.md)
- [failure-modes.md](failure-modes.md)
- [observability.md](observability.md)
