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

## Related Docs

- [ai-interface.md](ai-interface.md)
- [message-schema.md](message-schema.md)
- [failure-modes.md](failure-modes.md)
- [observability.md](observability.md)
