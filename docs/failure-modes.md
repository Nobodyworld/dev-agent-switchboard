# Failure Modes and Mitigations

This guide catalogues the most common operational failures seen when running the
Switchboard orchestration router. Each entry summarises symptoms, how to
identify the problem using built-in tooling, and the recommended remediation.

## Database Connectivity Loss

- **Symptoms** – `/health/ready` returns HTTP 503 with `database: false`; API
  endpoints return 500 errors referencing SQLAlchemy connection failures.
- **Detection** – Monitor the readiness probe or check application logs for
  `OperationalError`. The local runner will repeatedly receive `reason:
  "no_available_tasks"` because leases cannot be created.
- **Mitigation** – Restore database connectivity and restart the API process if
  connection pools need to be re-established. The readiness probe will flip to
  `ok: true` once connectivity returns.

## File Store Unavailable

- **Symptoms** – `/health/ready` returns HTTP 503 with `storage: false`; file
  upload attempts respond with 500 errors citing `file storage is not writable`.
- **Detection** – Inspect filesystem permissions and ensure the configured
  `FILES_ROOT` path exists. Readiness probes invoke `ensure_root()` and surface
  failures immediately.
- **Mitigation** – Correct permissions or mount points, then retry readiness. No
  restart is required once the directory becomes writable.

## Lease Contention or Expiration

- **Symptoms** – Agents receive `reason: "task_not_available"` during checkout
  or heartbeats return `ok: false` because another agent owns the lease.
- **Detection** – Review task details via `/api/tasks` to confirm status and
  `completed_notes`. The plan broadcast (WebSocket `/ws/plan`) includes the
  active lease holder in `TaskEnvelope.lease` metadata.
- **Mitigation** – Ensure agents heartbeat within the configured lease window.
  Operators can call `/api/tasks/{id}/abandon` to release tasks that are stuck
  after the lease expires.

## Rate Limit Exhaustion

- **Symptoms** – Rapid polling of `/health` or other endpoints yields HTTP 429
  responses with a `Retry-After` header.
- **Detection** – `server/middleware/rate_limit.py` emits metrics through the
  configured callback. The client SDK exposes the last checkout reason to help
  confirm whether throttling or empty queues caused a denial.
- **Mitigation** – Increase the rate limit via environment variables or adjust
  agent polling cadence. Trusted agents can be whitelisted using the existing
  configuration knobs.

## Local Runner Misconfiguration

- **Symptoms** – `scripts/local_runner.py` exits with connection errors or loops
  indefinitely without heartbeats.
- **Detection** – Run the runner with `--base-url` explicitly pointing at the
  server and verify `/health/ready` responds with `ok: true`. Inspect the runner
  logs; a successful checkout logs the task title before any action.
- **Mitigation** – Supply the correct base URL, ensure the agent has sufficient
  permissions, and use `--auto-complete` when you want the runner to finish
  tasks automatically.
