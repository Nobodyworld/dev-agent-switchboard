
# Switchboard — Real‑Time Agent Task Switchboard & Live File Host

Switchboard is a small, production‑leaning FastAPI service that:

- Hosts a **live, editable plan** (DAG of tasks with dependencies) that agents can **discover, check out, heartbeat, complete, or abandon**.
- Broadcasts **real‑time updates** (WebSockets) when tasks change state or plans/files update.
- Serves a **live file mirror** under predictable URLs so any LLM/agent can retrieve the latest docs **without re‑uploading**.
- Ships a lightweight admin UI with color-coded status badges and a friendly empty state so task filters always communicate what you're seeing.
- Ships with **AGENTS.md** and a **.agent/PLANS.md** template aligned with the ExecPlan pattern.
- Includes a **Python client** for agent integrations and **Docker** packaging.
- Documents the full stack layout in [docs/architecture.md](docs/architecture.md).

## Quickstart (local)

Requirements: Python 3.11+, Node not required. (UI is static HTML+HTMX.)

### 1. Create & activate a virtual environment

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

### 2. Install server dependencies

```bash
pip install -r server/requirements-dev.txt
```

Unix-like shells can run `make setup` to create the virtual environment and
install the same dependencies in one step. On Windows, prefer the explicit
commands above (or adapt them for `python -m pip`).

### 3. Run the API + UI locally

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

### 4. Run the test suite and quality gates

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

## Configuration

Switchboard reads its operational settings from environment variables. Copy
`.env.example` to `.env` (or export variables in your shell) to tune runtime
behavior:

* `DATABASE_URL` — SQLAlchemy connection string (defaults to SQLite).
* `STORAGE_ROOT` / `FILES_ROOT` — filesystem locations for live file storage.
* `SWITCHBOARD_RATE_LIMIT_*` — request limiter configuration. Invalid values
  now raise a clear startup error instead of silently falling back to
  defaults.
* Optional observability controls such as `SWITCHBOARD_LOGGING_LEVEL`,
  `SWITCHBOARD_METRICS_PATH`, and `SWITCHBOARD_TRACING_EXPORTER`.

Refer to the [Architecture overview](ARCHITECTURE.md) for additional context
on where each setting is consumed.

## Continuous integration

Incoming pull requests are validated by the `CI` GitHub Actions workflow. The
pipeline mirrors the local setup described above:

1. Set up Python 3.11 and install development dependencies from
   `server/requirements-dev.txt`.
2. Execute the test suite via `python scripts/run_pytest.py`.
3. Optionally run `make fmt`, `make lint`, and `make typecheck` when the
   corresponding repository variables (`CI_RUN_FMT`, `CI_RUN_LINT`,
   `CI_RUN_TYPECHECK`) are set to `true`, or when triggering the workflow
   manually with the dispatch inputs enabled.

Repository maintainers can enable the optional gates globally by defining the
above variables under **Settings → Variables → Repository variables**, or opt
into them per run through the "Run workflow" dialog in GitHub's UI.

### Sample API flows (curl)

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

### Optional: Python CLI helper

The repository ships a minimal Python helper that behaves like a CLI. With the virtual environment activated:

```bash
python -m client.python.examples.agent_example
```

## Observability (logging, metrics, tracing)

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

### Local usage

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
## Rate limiting

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

## Project structure

- `AGENTS.md` — guidance for agents, including ExecPlan trigger.
- `.agent/PLANS.md` — the ExecPlan spec template the agents can fill/obey.
- `server/` — FastAPI app, SQLite via SQLAlchemy, WebSockets, HTMX UI.
- `client/python/` — Python client for agent use (checkout/heartbeat/complete).
- `web/` — lightweight admin UI (HTMX + Tailwind CDN).
- `ops/` — Docker files.
- `server/tests/` — pytest scenarios for core flows.

---

**Why this exists:** Agents (Codex, Copilot Agents, etc.) need a single, live source of truth to coordinate work: a plan that can **change in flight**, a **queue** that respects **dependencies**, and a place to **publish documents** that any LLM can fetch by URL. Switchboard gives you all three with minimal overhead.
