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

## Architecture Overview

Switchboard is intentionally modular:

- **Router & API** – `server/app.py` exposes REST, WebSocket, and health
  endpoints. Queue orchestration occurs in `server/application/task_service.py`
  backed by shared dataclasses in `server/domain/` and `server/interfaces.py`.
- **Domain Logic** – `server/domain/` and `server/application/task_service.py` encapsulate task lifecycle rules,
  leases, and dependency evaluation.
- **Client Toolkit** – `client/python/switchboard_client.py` and
  `scripts/local_runner.py` provide a Python API and executable runner that
  exercise the router.
- **Maintenance Mode** – `server/application/system_state_service.py` persists
  the global maintenance flag while the CLI (`switchboard-cli maintenance`) and
  web dashboard keep operators informed and in control.

See [Architecture](architecture.md) for diagrams and deeper discussion, and
consult the top-level [Architecture Overview](../ARCHITECTURE_OVERVIEW.md) for a
component map of the updated extension pipeline.

## Message Schema

The router exchanges structured payloads defined in `server/interfaces.py`. Key
structures include:

- **TaskEnvelope** – wraps queue metadata, task payload, and active lease
  details.
- **HealthStatus** – aggregates liveness and readiness checks with per-probe
  booleans.

Consult the [Message Schema reference](message-schema.md) for serialized
examples and field definitions.

## Failure Modes

Operational concerns—from database outages to lease contention—are captured in
[Failure Modes](failure-modes.md). Each scenario includes detection guidance and
recommended remediation steps.

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

- [Architecture](architecture.md)
- [Architecture Overview](../ARCHITECTURE_OVERVIEW.md)
- [Message Schema](message-schema.md)
- [Failure Modes](failure-modes.md)
- [CLI Runtime Guide](cli-runtime.md)
- [Extension Guide](../EXTENSION_GUIDE.md)
- [Automation Handbook](../AUTOMATION.md)
- [Incident Response Runbook](incident-response.md)
- [Dependency & License Audit](DEPENDENCIES.md)
- [README](../README.md)
- [CHANGELOG](../CHANGELOG.md)
- [TODO Issues](TODO-ISSUES.md)

For historical documents that have not yet been migrated, see `docs/INDEX.md`.
