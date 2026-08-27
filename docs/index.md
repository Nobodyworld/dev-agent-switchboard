# Switchboard Documentation Hub

Welcome to the Switchboard operator and agent guide. This site explains how the
queue and agent orchestration router is structured, how to run it locally, and
how to integrate agents safely.

## Quick Start

1. **Install dependencies**

   ```bash
   make install
   ```

2. **Start the API and dashboard**

   ```bash
   make serve
   ```

3. **Verify health checks**

   ```bash
   curl http://localhost:8000/health/live
   curl -i http://localhost:8000/health/ready
   ```

4. **Run the local runner**

   ```bash
   python scripts/local_runner.py --base-url http://localhost:8000 --once
   ```

   The runner registers an agent, attempts a checkout, and optionally completes
   a task when `--auto-complete` is supplied. See the [end-to-end
   example](#end-to-end-example) for a fuller walkthrough.

5. **Review the endpoint reference**

   Start with [API.md](API.md) for the endpoint index, then use
   [ai-interface.md](ai-interface.md) for payload details.

## Architecture Overview

Switchboard is intentionally modular:

- **Router & API** – `server/app.py` exposes REST, WebSocket, and health
  endpoints. Queue orchestration occurs in `server/application/task_service.py`
  backed by domain records in `server/domain/` and the Pydantic schemas in
  `server/schema.py`.
- **Domain Logic** – `server/domain/` and `server/application/task_service.py` encapsulate task lifecycle rules,
  leases, and dependency evaluation.
- **Client Toolkit** – `client/python/switchboard_client.py` and
  `scripts/local_runner.py` provide a Python API and executable runner that
  exercise the router.
- **Maintenance Mode** – `server/application/system_state_service.py` persists
  the global maintenance flag while the CLI (`switchboard-cli maintenance`) and
  web dashboard keep operators informed and in control.

See [Architecture](architecture.md) for diagrams and deeper discussion, and
consult the top-level [Architecture Overview](architecture/architecture-overview.md) for a
component map of the updated extension pipeline.

The implemented [Local Execution Broker Architecture](architecture/local-execution-broker.md)
defines approved work orders, pull-based local workers, trusted command
manifests, exact-SHA validation, and structured evidence. The
[validate-switchboard manifest](examples/execution/validate-switchboard-v1.yaml)
is a stable contract reference; use the Validation Broker and
[local-worker operations guide](operations/local-worker.md) for the current
operator path.

## Message Schema

The router exchanges structured payloads defined in `server/schema.py`. Core
structures include:

- **TaskOut** – immutable task payload returned by `/api/tasks` and checkout
  responses.
- **PlanOut** – WebSocket broadcast payload capturing the current plan version
  and serialized tasks.
- **HealthStatus** – aggregates liveness and readiness checks with per-probe
  booleans.

Consult the [Message Schema reference](message-schema.md) for serialized
examples and field definitions.

## Failure Modes

Operational concerns—from database outages to lease contention—are captured in
[Failure Modes](failure-modes.md). Each scenario includes detection guidance and
recommended remediation steps.

## Observability

Review the [Observability Playbook](observability.md) for guidance on enabling
metrics, tracing, and the audit feed. The playbook documents health endpoint
semantics, header propagation, and operational checklists for automation.

## Maintenance Mode

Maintenance mode pauses new checkouts so you can apply migrations or debug
issues without juggling active agents:

1. Enable maintenance with the CLI:

   ```bash
   switchboard-cli maintenance --base http://localhost:8000 --enable --message "Applying migrations" --admin-token "$SWITCHBOARD_ADMIN_TOKEN"
   ```

2. The dashboard banner switches to an amber warning, and `switchboard-cli run`
   exits immediately with the operator-supplied message.

3. When ready, disable maintenance with the CLI or the dashboard form. The
   server broadcasts the change to all WebSocket listeners so agents can resume
   work.

The admin token is optional in development but should be configured in
production via `SWITCHBOARD_ADMIN_TOKEN`.

## Task Analytics

Track backlog health without scanning every task manually:

- **API:** `GET /api/tasks/analytics` returns totals for pending, in-progress,
  ready, and blocked tasks alongside dependency statistics.
- **CLI:** `switchboard-cli stats --base http://localhost:8000` renders the
  analytics table in the terminal; add `--json` to consume the raw payload in
  scripts.
- **UI:** The dashboard now includes a Task Analytics card summarising ready
  versus blocked work and dependency density with live refresh controls.

## End-to-End Example

Follow these steps to process a task locally:

1. Seed a task using the REST API:

   ```bash
   http POST http://localhost:8000/api/tasks title="Sample" description="Demo"
   ```

2. Run the local runner in auto-complete mode:

   ```bash
   python scripts/local_runner.py --base-url http://localhost:8000 --auto-complete --completion-notes "Verified locally"
   ```

3. Observe the task transition to `completed` via the dashboard or `http
   http://localhost:8000/api/tasks`.

## Additional Resources

- [Project ruleset](../PROJECT_RULESET.md)
- [Architecture](architecture.md)
- [API reference](API.md)
- [Architecture overview](architecture/architecture-overview.md)
- [Local execution broker architecture](architecture/local-execution-broker.md)
- [Execution manifest example](examples/execution/validate-switchboard-v1.yaml)
- [Message Schema](message-schema.md)
- [Failure Modes](failure-modes.md)
- [CLI Runtime Guide](cli-runtime.md)
- [Extension guide](guides/extension-guide.md)
- [Automation handbook](guides/automation.md)
- [Incident Response Runbook](incident-response.md)
- [Future-Proofing Guide](future-proofing.md)
- [Dependency & License Audit](dependencies.md)
- [Websocket Backoff Follow-up Audit (2025-11-06)](reports/audit-2025-11-06-websocket-backoff.md)
- [README](../README.md)
- [CHANGELOG](../CHANGELOG.md)
- [Task Backlog](TASKLIST.md)

For historical documents that have not yet been migrated, see `docs/navigation-index.md`.
