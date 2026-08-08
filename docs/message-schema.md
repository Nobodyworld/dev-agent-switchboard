# Message Schema Reference

This reference documents the JSON contracts exchanged between agents, the
dashboard, and the Switchboard orchestration router. Every structure is backed
by Pydantic models in `server/schema.py` or, for the isolated execution
control plane, `server/execution/schemas.py`.

## TaskOut

`TaskOut` represents an immutable task payload returned by `/api/tasks`,
`/api/tasks/{id}`, and successful checkouts:

```json
{
  "id": 42,
  "title": "Publish documentation",
  "description": "Refresh message schema reference",
  "status": "in_progress",
  "completed_notes": null,
  "depends_on": [21, 23]
}
```

- **status** – Enumerated value from `TaskStatus`.
- **depends_on** – Ordered task identifiers representing prerequisites.
- **completed_notes** – Persisted operator or agent notes (may be `null`).

## CheckoutOut

The `/api/tasks/checkout` endpoint returns a `CheckoutOut` payload:

```json
{
  "task": {
    "id": 42,
    "title": "Publish documentation",
    "description": "Refresh message schema reference",
    "status": "in_progress",
    "completed_notes": null,
    "depends_on": [21, 23]
  },
  "reason": null,
  "message": null
}
```

- **task** – Populated `TaskOut` when a lease is granted; omitted when checkout
  fails.
- **reason** – Machine-readable failure code (`"no_available_tasks"`,
  `"task_not_found"`, `"task_not_available"`, or `"maintenance_mode"`).
- **message** – Optional human-readable explanation accompanying the failure
  reason.

Clients should persist `reason` (the Python SDK stores it on
`SwitchboardClient.last_checkout_reason`) to inform backoff policies.

## Execution WorkOrder

`WorkOrderCreateIn` is a strict request model for
`POST /api/execution/work-orders`. It is deliberately identity- and
policy-only: callers supply a manifest name/version and safe policy metadata,
while Switchboard resolves the immutable manifest digest from its own trusted
registry.

```json
{
  "schema_version": 1,
  "repository_full_name": "Nobodyworld/dev-agent-switchboard",
  "commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "manifest": {
    "name": "validate-switchboard",
    "version": "1",
    "parameters": {}
  },
  "required_capabilities": {"docker": false},
  "permitted_paths": ["server", "tests"],
  "approval_policy": "explicit",
  "timeout_seconds": 3600,
  "network_policy": "worker_restricted",
  "repository_write": false,
  "routing_policy": "cheapest_capable",
  "maximum_cost_units": 20,
  "required_quota_units": 4,
  "preferred_executor": null
}
```

- **commit_sha** – Exactly 40 hexadecimal characters; abbreviated SHAs are
  rejected.
- **manifest** – A server-controlled immutable name/version identity. The
  response adds `manifest_digest`; callers cannot submit or override it.
- **repository_write** – Must be `false` in Phase 1.
- **routing_policy** – Strictly `first_available` (the omitted default) or
  `cheapest_capable`. The latter routes only among fully eligible actively
  polling trusted local workers with operator-owned profiles.
- **maximum_cost_units / required_quota_units** – Bounded non-negative integers
  used for abstract local comparison and quota reservation. The legacy
  floating `cost_ceiling` remains compatible but is not authoritative.
- **preferred_executor** – Optional hard pin to a known worker. It overrides
  score ranking but no approval, health, poll, capacity, capability, network,
  read-only, cost, profile, or quota check and never falls back.
- **strict fields** – Unknown fields, including `command`, `command_string`,
  `argv`, `script`, and `executable_path`, are rejected with validation errors.
  Those executable-shaped keys are also rejected recursively inside caller
  metadata such as manifest parameters, capability declarations, resource
  metadata, and result/evidence placeholders.

`WorkOrderOut` persists the full policy snapshot, approval/lifecycle
timestamps, attempt count, terminal reason, resolved manifest identity, and
optional compact route provenance. Provenance contains only the routing schema
and policy, selected worker/profile revision, estimated cost, required/reserved
quota, reservation state, eligible count, pin flag, bounded reason, and
decision timestamp. It is separate from `TaskOut` and never changes task-DAG
records.

## Execution lifecycle

`WorkOrderStatus` values are:

`pending_approval`, `approved`, `queued`, `assigned`, `running`, `succeeded`,
`failed`, `timed_out`, `cancelled`, `rejected`, and `expired`.

| Current state | Legal next state(s) |
| --- | --- |
| `pending_approval` | `approved`, `queued` (approve-and-queue), `rejected`, `cancelled` |
| `approved` | `queued`, `cancelled`, `expired` |
| `queued` | `assigned`, `cancelled`, `expired` |
| `assigned` | `running`, terminal result, `cancelled`, `queued` after stale lease expiry |
| `running` | terminal result, `queued` after stale lease expiry |
| terminal state | none; terminal records are immutable |

An `ExecutionRun` records a single attempt with its own status, assignment and
heartbeat timestamps, cleanup/evidence placeholders, and a bounded result
summary. A unique active execution lease associates at most one active run with
a work order; deleting that lease on terminal completion preserves run history.
Stale lease expiry terminalizes the old run as `timed_out` and requeues the
nonterminal work order, so the next checkout receives a higher attempt number.

## Worker and checkout payloads

`WorkerRegistrationIn` declares a stable `worker_id`, display/platform details,
tool and browser capabilities, capacity, supported network policy, and a
required `repository_write_capability: false`. The same Phase 1 admin token
temporarily protects worker operations. Registration and heartbeat reject
routing-profile fields and `last_checkout_poll_at`; every known authenticated
checkout records that timestamp from server time for the requester only.

`POST /api/execution/checkout` accepts only:

```json
{"worker_id": "local-linux-worker"}
```

It returns an `ExecutionRunOut` when one worker wins the atomic claim, or a
normal `200` payload such as the following when nothing can be assigned:

```json
{
  "run": null,
  "reason": "capability_mismatch",
  "mismatch_reasons": ["docker_not_available"]
}
```

For cheapest-capable work, other bounded empty-checkout reasons include
`better_candidate_active`, `preferred_executor_unavailable`,
`routing_profile_missing`, `routing_profile_disabled`,
`worker_heartbeat_stale`, `worker_checkout_poll_stale`,
`routing_cost_ceiling_exceeded`, `routing_quota_insufficient`, and
`routing_reservation_conflict`. Worker capacity, quota, work-order claim, run,
lease, and route provenance commit or roll back together.

`ExecutionCompletionIn` accepts an owned worker ID and exactly one terminal
status: `succeeded`, `failed`, `timed_out`, or `cancelled`. It records only
bounded metadata; it does not execute commands or accept executable steps.

## CompleteResponse

Completing a task responds with `CompleteResponse`:

```json
{
  "ok": true,
  "notes": "Verified locally"
}
```

- **ok** – Indicates whether the completion succeeded.
- **notes** – Normalized completion notes persisted on the task (may be `null`).

When completion succeeds, the WebSocket broadcaster emits a `plan_version`
payload (see `PlanOut` below) containing the updated task list and version.

## PlanOut

Plan broadcasts and `GET /api/plan` share the `PlanOut` payload:

```json
{
  "version": 17,
  "updated_at": "2025-10-26T03:15:40.124720+00:00",
  "tasks": [
    {
      "id": 42,
      "title": "Publish documentation",
      "description": "Refresh message schema reference",
      "status": "in_progress",
      "completed_notes": null,
      "depends_on": [21, 23]
    }
  ]
}
```

- **version** – Monotonically increasing integer indicating the latest plan
  revision.
- **updated_at** – UTC timestamp of the plan snapshot.
- **tasks** – Array of `TaskOut` objects.

## HealthStatus

Health probes share the `HealthStatus` payload:

```json
{
  "ok": true,
  "checks": {
    "process": true,
    "database": true,
    "storage": true
  },
  "version": "0.1.0",
  "uptime_seconds": 23.4,
  "started_at": "2025-10-26T02:45:19.120418+00:00"
}
```

- `/health/live` always returns `process: true` and reflects application
  version.
- `/health/ready` toggles `database` and `storage` based on runtime probes.
  When any check fails the endpoint responds with HTTP 503 and `ok: false` while
  still emitting the body above.

## HealthEnvelopeOut

`/api/health` wraps both health probes to provide a single JSON response:

```json
{
  "ok": true,
  "liveness": {"ok": true, "checks": {"process": true}},
  "readiness": {"ok": true, "checks": {"database": true, "storage": true}}
}
```

- **ok** – `true` only when both liveness and readiness passed.
- **liveness/readiness** – `HealthStatus` payloads mirroring the individual
  `/health/live` and `/health/ready` endpoints. The API responds with HTTP 503
  when `ok` is `false` to integrate cleanly with load balancers.

## TelemetryReportOut

`/api/observability/telemetry` surfaces instrumentation posture via
`TelemetryReportOut`:

```json
{
  "generated_at": "2025-02-18T12:30:00Z",
  "logging": {
    "enabled": true,
    "configured": true,
    "details": {
      "request_id_header": "X-Request-ID"
    },
    "warnings": []
  },
  "metrics": {
    "enabled": false,
    "configured": false,
    "details": {
      "endpoint": "/metrics",
      "plan_observers": 3
    },
    "warnings": [
      "Prometheus instrumentation disabled; set SWITCHBOARD_ENABLE_METRICS=1 to expose /metrics."
    ]
  },
  "tracing": {
    "enabled": true,
    "configured": true,
    "details": {
      "exporter": "console"
    },
    "warnings": []
  },
  "request_id_header": "X-Request-ID",
  "health_endpoints": ["/health/live", "/health/ready", "/api/health"],
  "runtime": {
    "metadata": {
      "plan_snapshot": {
        "blocked_tasks": 1,
        "ready_tasks": 4,
        "version": 12
      }
    }
  }
}
```

- **logging/metrics/tracing** – `TelemetrySubsystemOut` structures with
  `enabled` and `configured` flags plus descriptive details/warnings.
- **request_id_header** – Header downstream systems should propagate.
- **health_endpoints** – Enumerates which health routes are exposed for load
  balancers or monitors.
- **runtime.metadata.plan_snapshot** – Present when the builtin plan snapshot
  extension has observed a broadcast.

## MetricsCatalogOut

`/api/observability/metrics` returns the analytics catalog so dashboards can
confirm whether builtin gauges are fresh without scraping `/metrics`:

```json
{
  "generated_at": "2025-02-18T12:30:00Z",
  "enabled": true,
  "last_updated_at": "2025-02-18T12:29:58Z",
  "status": {"pending": 3, "completed": 5},
  "readiness": {"ready": 4, "blocked": 1},
  "dependency": {"with_dependencies": 2, "without_dependencies": 6},
  "missing": {"tasks": 0, "edges": 0},
  "dependency_edges": 4.0,
  "average_dependencies": 1.5,
  "updated_timestamp": 1708259398.0
}
```

- **enabled** – Indicates whether Prometheus metrics are currently instrumented.
- **last_updated_at** – Timestamp of the last plan analytics broadcast that
  refreshed gauges (null when metrics have never run).
- **status/readiness/dependency/missing** – Gauge snapshots describing the task
  portfolio.
- **updated_timestamp** – Raw Unix timestamp of the last metrics update.

## DiagnosticsReportOut

`/api/diagnostics` returns `DiagnosticsReportOut` summarising package versions
and runtime state. See the endpoint documentation for detailed fields; the
payload is intentionally verbose to support operations automation.

## Agent Registration

`POST /api/agents` returns an `AgentRegistrationResponse`:

```json
{
  "ok": true,
  "agent_id": "local-runner"
}
```

- **ok** – Always `true`.
- **agent_id** – Canonical identifier used in checkout and heartbeat calls.
