
# Switchboard — Real‑Time Agent Task Switchboard & Live File Host

[![CI](https://github.com/openai/switchboard/actions/workflows/ci.yml/badge.svg)](https://github.com/openai/switchboard/actions/workflows/ci.yml)
[![Commitlint](https://github.com/openai/switchboard/actions/workflows/commitlint.yml/badge.svg)](https://github.com/openai/switchboard/actions/workflows/commitlint.yml)

## What

Switchboard is a small, production‑leaning FastAPI service that:

- Hosts a **live, editable plan** (DAG of tasks with dependencies) that agents can **discover, check out, heartbeat, complete, or abandon**.
- Broadcasts **real‑time updates** (WebSockets) when tasks change state or plans/files update.
- Serves a **live file mirror** under predictable URLs so any LLM/agent can retrieve the latest docs **without re‑uploading**.
- Ships a lightweight admin UI with color-coded status badges and a friendly empty state so task filters always communicate what you're seeing.
- Ships with **AGENTS.md** and a **.agent/PLANS.md** template aligned with the ExecPlan pattern.
- Includes a **Python client** and a **local runner** for agent integrations alongside container packaging.
- Surfaces a structured diagnostics snapshot (`/api/diagnostics`) and dashboard panel so operators can verify package versions, configuration, and feature toggles without leaving the app.
- Exposes `/api/health`, `/api/observability/telemetry`, and `/api/observability/metrics` so operators and agents can check readiness, instrumentation posture, and analytics catalogues without stitching multiple endpoints together.
- Publishes task analytics as Prometheus gauges on every plan broadcast so dashboards and alerting systems can track ready/blocked backlogs without polling the API.
- Bundles a plan snapshot extension that records the latest analytics for dashboards and incident responders.
- Documents the full stack layout in [docs/architecture.md](docs/architecture.md) and the new [documentation hub](docs/index.md).

## Why

- Provide a **single orchestration router** that stabilises the contract between queues, agents, and operator tooling.
- Make it easy to verify deployments via **health checks** and a **local runner** without authoring bespoke agents.
- Keep humans and automation in sync by mirroring live plans, live files, and failure diagnostics in one place.

## How

- **Router & Schemas** – `server/api/` provides the FastAPI routers and application factory, while `server/app.py` re-exports the assembled app alongside compatibility helpers. `server/schema.py` translates domain records from `TaskService` into immutable payloads returned by the API.
- **Domain & Application Layers** – `server/domain/` defines immutable task and lease records, while `server/application/task_service.py` orchestrates lifecycle rules through repository interfaces and triggers extension hooks (including plan observers).
- **Infrastructure Adapters** – `server/infrastructure/repositories.py` implements the repository interfaces against SQLAlchemy models, batching dependency lookups so task checkout avoids N+1 queries.
- **Health & Operations** – `/health/live` and `/health/ready` surface liveness and dependency status via the new `HealthStatus` schema; `docs/failure-modes.md` enumerates remediation steps.
- **Agent Toolkit** – `client/python/switchboard_client.py` exposes a resilient HTTP client while `scripts/local_runner.py` offers an executable agent loop for local testing.
- **Maintenance Controls** – `/api/system-state`, the CLI `switchboard-cli maintenance` command, and the web dashboard banner expose a shared maintenance mode switch with optimistic concurrency and WebSocket broadcasts so humans and agents remain in sync.

## Repository Essentials

- [SPEC.md](SPEC.md) captures the canonical project snapshot, governance
  expectations, and operational defaults.
- [STYLE-GUIDE.md](STYLE-GUIDE.md) documents the coding conventions shared by
  the server, client, and web dashboards.
- [TASKLIST.md](TASKLIST.md) is the authoritative backlog used to track ongoing
  work.
- [docs/README.md](docs/README.md) links to architecture deep dives, guides, and
  reports grouped by purpose.

## Documentation Map

Start with the [documentation hub](docs/index.md) for a curated quick start, message schema reference, and failure modes. The table below highlights common entry points:

| Topic | Start Here |
| --- | --- |
| Quick start, architecture, message schema | [docs/index.md](docs/index.md) – consolidated hub introduced in this release |
| Legacy navigation index | [docs/navigation-index.md](docs/navigation-index.md) – navigation map & module reference (`docs/_meta/navigation.yaml` exposes machine-readable nav) |
| System architecture & data flow | [docs/architecture/architecture.md](docs/architecture/architecture.md) – high-level responsibilities<br/>[docs/architecture/architecture-overview.md](docs/architecture/architecture-overview.md) – runtime topology diagrams |
| Operator & agent workflows | [README.md](README.md#quickstart-local) – quickstart, local runner, and CLI guidance<br/>[docs/ai-interface.md](docs/ai-interface.md) – endpoint matrix |
| Message schema details | [docs/message-schema.md](docs/message-schema.md) – serialized payloads and field definitions |
| Failure diagnostics | [docs/failure-modes.md](docs/failure-modes.md) – detection and mitigation guide |
| ExecPlan registry | [docs/execplan-registry-index.md](docs/execplan-registry-index.md) |
| Rate limiting design | [docs/rate-limiting-design.md](docs/rate-limiting-design.md) |
| Testing & quality reports | [docs/testing_report.md](docs/testing_report.md) |
| Documentation status & backlog | [docs/portal-status.md](docs/portal-status.md) |

Each document now shares terminology and links back to this README so contributors can pivot between operational, architectural, and API-focused guidance without guessing where to look. The refreshed [task backlog](TASKLIST.md) captures follow-up work discovered during the orchestration router stabilization.

Documentation is grouped by purpose: architecture references live under `docs/architecture/`, contributor handbooks and runbooks live under `docs/guides/`, reports and status digests live under `docs/reports/`, and historical artifacts are tucked into `docs/history/` for posterity.

## Architecture at a Glance

Switchboard follows a service-plus-client architecture:

```text
┌────────────────┐      REST & WS       ┌──────────────────────────┐
│  Agents / CLI  │ ───────────────────▶ │    FastAPI Application   │
│  (humans & AI) │ ◀─────────────────── │  (server/api → app.py)   │
└────────────────┘     plan updates     └────────────┬─────────────┘
                                                      │
                                                      ▼
                                  ┌──────────────────────────────┐
                                  │ Persistence & Domain Logic   │
                                  │ (server/models.py,           │
                                  │  server/application/task_service.py, │
                                  │  server/domain/, etc.) │
                                  └──────────────────────────────┘
                                                      │
                                                      ▼
                                  ┌──────────────────────────────┐
                                  │ Live Files & ExecPlan Index  │
                                  │ (server/file_store.py,       │
                                  │  server/execplan_registry.py)│
                                  └──────────────────────────────┘
```

- **FastAPI application (`server/api`, `server/app.py`)** exposes REST endpoints, WebSocket plan broadcasts, and the static operator UI. Middleware hooks add rate limiting and observability while the compatibility wrapper preserves legacy imports.
- **Domain logic (`server/domain/`, `server/application/`, `server/file_store.py`)** coordinates task lifecycle state, dependency enforcement, and content mirroring while keeping database access localized.
- **Client toolkit (`client/python/`)** wraps the HTTP API for both interactive humans (`switchboard_cli.py`) and automated agents.
- **Live files & ExecPlan registry** give agents durable documentation by persisting uploads to disk and serving digestible plan indexes, while the builtin `plan_metrics` observer keeps Prometheus gauges aligned with the latest plan snapshot.
- **Observability suite (`server/observability/health.py`, `server/observability/activity.py`)** orchestrates health probes, telemetry aggregation, and the rolling audit feed so operators can diagnose issues using correlated request and trace identifiers.

Operators can trace how a request moves from CLI to FastAPI to persistence by reading the matching sections in [docs/architecture/architecture.md](docs/architecture/architecture.md) and the annotated source files referenced above.

## API Quick Reference

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/agents` | `POST` | Register or idempotently confirm an agent identifier. |
| `/api/tasks` | `GET` | List tasks with dependency metadata; filter via `status`. |
| `/api/tasks` | `POST` | Create a task and optional dependency edges. |
| `/api/tasks/checkout` | `POST` | Lease the next available task; failures include a `reason`. |
| `/api/tasks/{id}/heartbeat` | `POST` | Extend the active lease for the agent that checked out the task. |
| `/api/tasks/{id}/complete` | `POST` | Mark a task complete and store optional notes. |
| `/api/tasks/{id}/abandon` | `POST` | Release the lease without completion. |
| `/api/tasks/analytics` | `GET` | Return aggregated task analytics including ready/blocked counts and dependency health. |
| `/health/live` | `GET` | Liveness probe returning the `HealthStatus` payload with `process` checks and probe observations. |
| `/health/ready` | `GET` | Readiness probe that validates database and storage access; returns HTTP 503 when dependencies fail and includes probe metadata for root-cause analysis. |
| `/api/health` | `GET` | JSON envelope combining liveness and readiness payloads; returns HTTP 503 when readiness fails. |
| `/api/observability/telemetry` | `GET` | Summarises logging, metrics, tracing, runtime metadata, and observability notes (requires admin token when configured). |
| `/api/observability/metrics` | `GET` | Exposes the Prometheus analytics catalog (enabled status, last updated timestamp, sample values). |
| `/api/observability/health` | `GET` | Aggregates liveness, readiness, and telemetry state into a single payload (requires admin token when configured). |
| `/api/observability/audit-feed` | `GET` | Returns the rolling in-memory audit feed captured by the builtin `activity_feed` extension (requires admin token when configured). |
| `/api/settings` | `GET` | Inspect rate limit and lease configuration (used by the CLI). |
| `/api/configuration` | `GET` | Retrieve a comprehensive configuration snapshot (settings, storage, database, runtime, warnings). |
| `/api/diagnostics` | `GET` | Retrieve runtime metadata, package versions, feature toggles, and system state for operators and UI diagnostics. |
| `/api/system-state` | `GET`, `PUT` | Inspect or toggle global maintenance mode. `PUT` requires the admin token when `SWITCHBOARD_ADMIN_TOKEN` is set. |
| `/api/files/{path}` | `PUT` | Upload live documentation available under `/live/<path>`. |
| `/ws/plan` | `GET` (WebSocket) | Stream plan version updates and deltas for UI/agent sync. |

See [docs/ai-interface.md](docs/ai-interface.md) for payload schemas, curl examples, and integration tips.

## Python Client Example

Use the packaged client to build agents or automation scripts without hand-crafting HTTP requests:

```python
from switchboard_client import SwitchboardClient

with SwitchboardClient("http://localhost:8000", "codex-1") as client:
    task = client.checkout()
    if task:
        print(f"Working on task {task['id']}: {task['title']}")
        # maintain the lease while performing work
        client.heartbeat(task["id"])
        client.complete(task["id"], notes="Implemented feature end-to-end")
    else:
        print(f"Checkout skipped: {client.last_checkout_reason or 'no tasks available'}")
```

The client automatically registers the agent, reuses a `requests.Session`, and exposes convenience helpers such as `get_settings()` and `upload_file()`.

### Maintenance Mode

Switchboard includes a coordinated maintenance toggle that pauses new task checkouts while allowing in-flight work to finish:

- **API:** `GET /api/system-state` returns the persisted flag, message, timestamp, and optimistic concurrency version. `PUT /api/system-state` updates the state and broadcasts the change to WebSocket listeners; set `SWITCHBOARD_ADMIN_TOKEN` to require `Authorization: Bearer <token>` for mutations.
- **CLI:** `switchboard-cli maintenance --base <url> [--enable|--disable] [--message <text>] [--expected-version <n>] [--admin-token <token>]` inspects and toggles the state without writing bespoke scripts. The interactive `switchboard-cli run` command refuses to start when maintenance is active and surfaces the operator-provided message.
- **Task analytics:** `switchboard-cli stats --base <url> [--json]` fetches aggregated ready/blocked counts and dependency health so operators can triage backlogs without opening the UI.
- **Configuration:** `switchboard-cli config --base <url> [--json]` prints the consolidated configuration snapshot (rate limits, storage health, database provenance, and warnings) and powers the new `make config` convenience target.
- **UI:** The dashboard shows an amber banner whenever maintenance is enabled and includes a guarded toggle form that stores the admin token locally and uses optimistic concurrency.

All channels share a single source of truth so operators can confidently pause checkouts during upgrades or incident response.

## CLI Runtime Summary

The `switchboard-cli run` command now prints a formatted runtime summary before
entering the task loop. It combines server-provided lease data with user
arguments using the helpers in `client/python/runtime_config.py`, then displays
the effective heartbeat cadence, polling intervals, and backoff multiplier in a
readable table. Any sanitisation warnings (for example, negative poll
intervals or missing lease information) are surfaced on **stderr** so scripts
can react without parsing the summary. Consult [docs/cli-runtime.md](docs/cli-runtime.md)
for a walkthrough of the start-up flow and warning catalogue.

Run `switchboard-cli maintenance --base http://localhost:8000 --enable --admin-token <token>` to toggle maintenance mode outside the interactive loop.

## End-to-End Example (Local Runner)

Use the packaged local runner to exercise the orchestration router without writing a custom agent:

```bash
make serve  # in a separate shell

http POST http://localhost:8000/api/tasks \
  title="Demo" description="Run the local runner"

python scripts/local_runner.py --base-url http://localhost:8000 --auto-complete --completion-notes "Verified locally"
```

The runner will register itself, lease the next task, maintain heartbeats while it works, and complete the task with the supplied notes. Re-run without `--auto-complete` to observe heartbeat-only behaviour (press `Ctrl+C` to stop the loop).

## Quickstart (Local)

Requirements: Python 3.11+, Node not required. (UI is static HTML+HTMX.)

### 1. Create & Activate a Virtual Environment

<details>
<summary><strong>macOS / Linux (bash, zsh)</strong></summary>

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

</details>

<details>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

</details>

<details>
<summary><strong>Windows (Command Prompt)</strong></summary>

```bat
python -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
```

</details>

### 2. Install Server Dependencies

```bash
pip install -r server/requirements-dev.txt
```

Unix-like shells can run `make setup` to create the virtual environment and
install the same dependencies in one step. On Windows, prefer the explicit
commands above (or adapt them for `python -m pip`).

### 3. Install Developer Tooling

```bash
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

This keeps formatting, linting, and commit message policies aligned with CI. See
[CONTRIBUTING](CONTRIBUTING.md) for more detail.

### 4. Run the API + UI Locally

```bash
python scripts/run_uvicorn.py
```

On Windows PowerShell:

```powershell
python .\scripts\run_uvicorn.py
```

Unix-like shells also expose a convenience target: `make run`. (The Makefile
uses POSIX-style activation; Windows users should rely on the Python helper
instead.)

Open the admin UI: <http://localhost:8000/>

### 5. Run the Test Suite and Quality Gates

```bash
python scripts/run_pytest.py
```

On Windows PowerShell:

```powershell
python .\scripts\run_pytest.py
```

Unix-like shells can alternatively run `make test`. Additional quality
automation is available through the following make targets:

* `make fmt` — format code using **black**.
* `make lint` — run the **ruff** static analysis checks.
* `make typecheck` — execute **mypy --strict** for the API and client.
* `make security` — scan the server code with **bandit**.
* `make qa` — run the full formatter, lint, type, test, and security suite.
* `make config` — invoke `switchboard-cli config` against `$API_BASE` to inspect the live configuration snapshot.

## Configuration

Switchboard reads its operational settings from environment variables. Copy
`.env.example` to `.env` (or export variables in your shell) to tune runtime
behavior:

* `DATABASE_URL` — SQLAlchemy connection string (defaults to SQLite).
* `STORAGE_ROOT` / `FILES_ROOT` — filesystem locations for live file storage.
* `SWITCHBOARD_RATE_LIMIT_*` — request limiter configuration. Invalid values
  now raise a clear startup error instead of silently falling back to
  defaults.
* `SWITCHBOARD_LEASE_SECONDS` — task lease duration in seconds (default `300`).
  Must be a positive integer; API clients adjust heartbeat cadence based on this
  value.
* Optional observability controls such as `SWITCHBOARD_LOGGING_LEVEL`,
  `SWITCHBOARD_METRICS_PATH`, and `SWITCHBOARD_TRACING_EXPORTER`.

Refer to the [Architecture overview](docs/architecture/architecture.md) for additional context
on where each setting is consumed.

## Continuous Integration

Incoming pull requests are validated by the [`CI`](.github/workflows/ci.yml)
workflow. Each stage runs in parallel for fast feedback and publishes artifacts
for reviewers:

1. **Lint** – `pre-commit run --all-files` (Ruff, Black, Prettier,
   `detect-secrets`, and hygiene checks).
2. **Typecheck** – `mypy --config-file mypy.ini server client scripts`.
3. **Test** – `pytest --maxfail=1 --disable-warnings --junitxml=reports/pytest.xml`.
4. **Docs** – [`lychee`](https://github.com/lycheeverse/lychee) verifies Markdown
   links across README, PLAN, REPORT, and `docs/`.

Secret scanning runs in parallel via
[`gitleaks`](https://github.com/gitleaks/gitleaks-action) on every push, and
commit messages are validated by [`commitlint`](commitlint.config.js) in a
dedicated workflow to enforce Conventional Commits.

### Sample API Flows (curl)

These are copy/paste friendly for macOS/Linux shells. On Windows PowerShell, replace the trailing backslashes (`\`) with backticks (`\``) and use double quotes for JSON payloads.

#### Seed a plan

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Initial plan setup","description":"Create seed tasks","depends_on":[]}'

curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Implement feature A","description":"Build A","depends_on":[1]}'
```

#### Inspect server settings

```bash
curl http://localhost:8000/api/settings | jq
```

The response surfaces rate limit thresholds, trusted client lists, and the
configured lease duration that agents should honor when sending heartbeats. When
settings are misconfigured the CLI emits warnings but falls back to safe
defaults so leases remain protected while operators investigate.

#### Agent lifecycle

```bash
# register an agent
curl -X POST http://localhost:8000/api/agents \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"codex-1"}'

# checkout an available task
curl -X POST "http://localhost:8000/api/tasks/checkout?agent_id=codex-1"

# heartbeat to extend lease
curl -X POST "http://localhost:8000/api/tasks/1/heartbeat?agent_id=codex-1"

# complete with notes
curl -X POST "http://localhost:8000/api/tasks/1/complete?agent_id=codex-1" \
  -H "Content-Type: application/json" \
  -d '{"notes":"Done"}'
```

#### Live files API

```bash
# write/update a live file from a local source file
curl -X PUT http://localhost:8000/api/files/docs/AGENTS.md \
  -H "Content-Type: text/markdown" \
  --data-binary @AGENTS.md

# fetch latest version
curl http://localhost:8000/live/docs/AGENTS.md
```

### Optional: Python CLI Helper

The repository ships a minimal Python helper that behaves like a CLI. With the virtual environment activated:

```bash
python -m client.python.examples.agent_example
```

## Developer Utilities & Quality Gates

- `scripts/dev.py bootstrap` provisions a `.venv` with development dependencies
  and installs pre-commit hooks.
- `scripts/dev.py coverage-gate` validates coverage JSON output against the
  ≥85% thresholds enforced in CI (see `.github/workflows/ci.yml`).
- `scripts/dev.py extensions` enumerates loaded extensions, contract notes, and
  observability registrations so operators can audit instrumentation quickly.
- `scripts/dev.py bump-version` updates `server/app.py`, `CHANGELOG.md`, and
  `RELEASE_NOTES.md` with a new semantic version stub.
- `make qa` now runs formatting, linting, typing, tests, security scans, and the
  coverage gate to mirror the CI pipeline locally.

See [the automation handbook](docs/guides/automation.md) for agent workflows and
[the extension guide](docs/guides/extension-guide.md) for custom plugin patterns.

## Community & Governance

- [CODE_OF_CONDUCT](CODE_OF_CONDUCT.md)
- [CONTRIBUTING](CONTRIBUTING.md)
- [SECURITY](SECURITY.md)
- [Support playbook](docs/guides/support.md)
- [Status digest](docs/reports/status.md)
- [Modernization roadmap](docs/guides/plan-operations.md)
- [Operations report](docs/reports/operations-report.md)
- [renovate.json](renovate.json) – automated dependency updates
- [Architecture overview](docs/architecture/architecture-overview.md)
- [Extension guide](docs/guides/extension-guide.md)
- [Automation handbook](docs/guides/automation.md)
- [Observability Playbook](docs/observability.md)

## Observability (Logging, Metrics, Tracing)

Switchboard now ships optional instrumentation modules that can be toggled entirely through environment variables. Each helper lives under `server/instrumentation/` and runs during application startup.

- **Logging** (`server/instrumentation/logging.py`)
  - Request IDs are attached via middleware and injected into log records through a `logging.Filter`. The middleware is on by default and can be disabled with `SWITCHBOARD_ENABLE_REQUEST_ID=0`.
  - Structured logging can be enabled with `SWITCHBOARD_ENABLE_STRUCTURED_LOGGING=1`. When set, the module uses `python-json-logger` to emit JSON to stdout.
  - Provide a logging configuration file with `SWITCHBOARD_LOGGING_CONFIG=/path/to/logging.ini`. The repository includes `ops/logging.ini`, which wires JSON handlers for uvicorn and application logs.

- **Metrics** (`server/instrumentation/metrics.py`)
  - Prometheus instrumentation is powered by `prometheus-fastapi-instrumentator` and is disabled by default.
  - Turn it on with `SWITCHBOARD_ENABLE_METRICS=1`. The metrics endpoint defaults to `/metrics` and can be overridden with `SWITCHBOARD_METRICS_PATH`.

- **Tracing** (`server/instrumentation/tracing.py`)
  - OpenTelemetry support instruments FastAPI and emits spans via either the console exporter (default) or OTLP. Enable it with `SWITCHBOARD_ENABLE_TRACING=1`.
  - Set `SWITCHBOARD_TRACING_EXPORTER=otlp` to use the OTLP HTTP exporter. Standard `OTEL_EXPORTER_OTLP_*` variables are honored.
  - The module can read an optional YAML file referenced by `SWITCHBOARD_OTEL_CONFIG`. The included `ops/otel.yaml` demonstrates how to define the necessary environment variables for Docker deployments.

### Local Usage

For ad-hoc local runs, export the desired environment variables before invoking uvicorn:

```bash
export SWITCHBOARD_ENABLE_STRUCTURED_LOGGING=1
export SWITCHBOARD_LOGGING_CONFIG="$(pwd)/ops/logging.ini"
export SWITCHBOARD_ENABLE_METRICS=1
export SWITCHBOARD_ENABLE_TRACING=1
uvicorn server.app:app --reload --host 0.0.0.0 --port 8000
```

When `SWITCHBOARD_LOGGING_CONFIG` is set, uvicorn automatically picks up the shared formatter, so no additional CLI flags are required.

### Docker Compose

The Compose file (`ops/docker-compose.yml`) mounts the default observability configs into the container. To enable instrumentation, populate `ops/.env` (or export variables in your shell) with values such as:

```bash
SWITCHBOARD_LOGGING_CONFIG=/app/ops/logging.ini
SWITCHBOARD_ENABLE_STRUCTURED_LOGGING=1
SWITCHBOARD_ENABLE_METRICS=1
SWITCHBOARD_ENABLE_TRACING=1
SWITCHBOARD_OTEL_CONFIG=/app/ops/otel.yaml
```

Restart the stack (`docker compose --project-directory ops up --build`) and the service will emit JSON logs, expose `/metrics`, and initialize tracing with the parameters from `ops/otel.yaml`.
The script registers an agent, polls for work, heartbeats while "working", and completes tasks when finished. If you are using a fresh environment just for the client, install `requests` first (`python -m pip install requests`).

## Docker

The Docker setup in `ops/` bind-mounts host directories so you can persist
Switchboard data between container runs. To start it locally:

1. Create the directories that are mounted into the container (from the repo
   root):

   ```bash
   mkdir -p storage .agent
   ```

2. Copy the example environment file and adjust `PORT` if you already have a
   service listening on port 8000:

   ```bash
   cp ops/.env.example ops/.env
   # edit ops/.env if you need to change PORT
   # Optionally override persistence locations:
   # DATABASE_URL=sqlite+aiosqlite:////absolute/path/to/switchboard.db
   # STORAGE_ROOT=/absolute/path/to/storage
   # FILES_ROOT=/absolute/path/to/storage/files
   ```

3. Build and launch the stack:

   ```bash
   docker compose -f ops/docker-compose.yml up --build
   ```

The compose file defines a health check that waits for `http://localhost:8000/health`
to return `200 OK` before marking the container as healthy.

By default the application stores its SQLite database and uploaded files inside the
container's `/app` directory. Set `DATABASE_URL`, `STORAGE_ROOT`, or `FILES_ROOT`
in `ops/.env` (or your shell) to persist data to alternative locations.
## Rate Limiting

Switchboard ships with an in-process request rate limiter to protect the API from
abusive clients while keeping trusted agents unthrottled. The middleware limits
requests per client IP over a sliding window and can be configured with
environment variables (also surfaced in `ops/.env.example`):

- `SWITCHBOARD_RATE_LIMIT_REQUESTS` – maximum requests allowed within the window
  (default `120`). Set to `0` to disable rate limiting.
- `SWITCHBOARD_RATE_LIMIT_WINDOW_SECONDS` – window size in seconds (default `60`).
- `SWITCHBOARD_RATE_LIMIT_TRUSTED_BYPASS` – comma-separated list of client IPs
  that should bypass rate limiting. The middleware checks the first value in the
  `X-Forwarded-For` header before falling back to the connection's remote
  address.

Adjust these variables locally or in container deployments to tune throughput.

## Project Structure

- `AGENTS.md` — guidance for agents, including ExecPlan trigger.
- `.agent/PLANS.md` — the ExecPlan spec template the agents can fill/obey.
- `server/` — FastAPI app, SQLite via SQLAlchemy, WebSockets, HTMX UI.
- `client/python/` — Python client for agent use (checkout/heartbeat/complete).
- `web/` — lightweight admin UI (HTMX + Tailwind CDN).
- `ops/` — Docker files.
- `server/tests/` — pytest scenarios for core flows.

---

**Why this exists:** Agents (Codex, Copilot Agents, etc.) need a single, live source of truth to coordinate work: a plan that can **change in flight**, a **queue** that respects **dependencies**, and a place to **publish documents** that any LLM can fetch by URL. Switchboard gives you all three with minimal overhead.
