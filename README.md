
# Switchboard — Real-Time Agent Task Switchboard & Live File Host

[![CI](https://github.com/Nobodyworld/dev-agent-switchboard/actions/workflows/ci.yml/badge.svg)](https://github.com/Nobodyworld/dev-agent-switchboard/actions/workflows/ci.yml)
[![Commitlint](https://github.com/Nobodyworld/dev-agent-switchboard/actions/workflows/commitlint.yml/badge.svg)](https://github.com/Nobodyworld/dev-agent-switchboard/actions/workflows/commitlint.yml)

Switchboard coordinates agent work against a shared task graph.
It provides a FastAPI backend, a dashboard, REST and WebSocket APIs, a Python client, and live-file hosting for agent-readable docs.

## What It Does

- Tracks tasks with dependencies and lease-based ownership.
- Lets agents check out, heartbeat, complete, and abandon work safely.
- Broadcasts plan updates over `/ws/plan` so the dashboard and agents stay in sync.
- Hosts mutable reference files under `/live/...` with optional admin-token protection.
- Exposes diagnostics, health, analytics, and observability endpoints for operators.

## Start Here

- [docs/index.md](docs/index.md) for the documentation hub.
- [docs/API.md](docs/API.md) for the endpoint index.
- [docs/architecture/architecture.md](docs/architecture/architecture.md) for the system layout.
- [docs/ai-interface.md](docs/ai-interface.md) for payloads and integration guidance.
- [docs/TASKLIST.md](docs/TASKLIST.md) for the active backlog.

## Quickstart

Requirements: Python 3.11+. Node.js v18+ is only needed for the websocket backoff test module.

1. Create a virtual environment.

```bash
python -m venv .venv
```

macOS/Linux:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Windows Command Prompt:

```bat
.\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
```

1. Install dependencies.

```bash
pip install -r server/requirements-dev.txt
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

1. Run the API and dashboard.

```bash
python scripts/run_uvicorn.py
```

Open <http://localhost:8000/>.

1. Seed a task and run an agent.

```bash
http POST http://localhost:8000/api/tasks \
  title="Demo" description="Run the local runner"

python scripts/local_runner.py --base-url http://localhost:8000 --auto-complete --completion-notes "Verified locally"
```

1. Run tests.

```bash
python scripts/run_pytest.py
```

## Two-Agent Demonstration

The repository now includes automated coverage for this sequence:

- Task A starts ready.
- Agent 1 leases Task A.
- Agent 1 heartbeats and completes Task A.
- Task B unlocks.
- Agent 2 leases Task B.
- WebSocket plan broadcasts update the dashboard state.

See [server/tests/test_websocket_plan.py](server/tests/test_websocket_plan.py) and [web/tests/test_ui.py](web/tests/test_ui.py).

## Configuration

Key environment variables:

- `DATABASE_URL` for the database connection.
- `STORAGE_ROOT` and `FILES_ROOT` for live file storage.
- `SWITCHBOARD_LEASE_SECONDS` for lease duration.
- `SWITCHBOARD_ADMIN_TOKEN` for privileged mutations.
- `SWITCHBOARD_MAX_LIVE_FILE_BYTES` for upload limits.
- `SWITCHBOARD_RATE_LIMIT_*` for request throttling.

See [docs/architecture/architecture.md](docs/architecture/architecture.md) and [docs/observability.md](docs/observability.md) for operational detail.

## Developer Utilities

- `scripts/dev.py bootstrap` provisions a `.venv` and installs hooks.
- `scripts/dev.py coverage-gate` validates coverage JSON against CI thresholds.
- `scripts/dev.py extensions` lists loaded extensions and observability registrations.
- `scripts/dev.py bump-version` updates versioned release surfaces.
- `make qa` runs formatting, linting, typing, tests, security scans, and coverage gates.

## Governance

- [LICENSE](LICENSE)
- [SECURITY](SECURITY.md)
- [CONTRIBUTING](CONTRIBUTING.md)
- [CODE_OF_CONDUCT](CODE_OF_CONDUCT.md)
- [docs/guides/support.md](docs/guides/support.md)

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
