# Switchboard

**Real-time agent task coordination with dependency-aware leasing and live-file hosting.**

Switchboard coordinates multiple agents against a shared task graph. It gives agents a single place to discover ready work, lease tasks, publish live reference files, and observe plan updates without building a custom orchestration service for every project.

## What It Demonstrates

- **Dependency-aware task coordination**: model work as tasks with prerequisites and unlock downstream work as dependencies complete.
- **Lease-based ownership**: let agents check out work while reducing duplicate execution through ownership and expiry semantics.
- **Live state synchronization**: broadcast plan changes to the dashboard and connected clients over WebSockets.
- **Live-file hosting**: publish mutable reference documents that agents can fetch by URL, with admin-token protection available for mutation endpoints.
- **Operational visibility**: expose health/readiness probes, diagnostics, metrics hooks, and structured logging patterns.

## Why It Matters

Autonomous coding agents, script runners, and human reviewers need a shared source of truth while work is in flight:

- a plan that changes as tasks complete;
- a queue that respects dependencies and avoids duplicate ownership;
- a lightweight document surface for prompts, checklists, and runtime notes;
- a dashboard that makes coordination state visible.

Switchboard is a small reference implementation of that coordination layer.

## Quick Start

### 1. Set Up

```bash
# Clone and enter repo
git clone https://github.com/Nobodyworld/dev-agent-switchboard.git
cd dev-agent-switchboard

# Create Python 3.11+ virtual environment
python -m venv .venv

# Activate the environment
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r server/requirements-dev.txt
```

### 2. Run the Server

```bash
python scripts/run_uvicorn.py
```

Open [http://localhost:8000/](http://localhost:8000/) to view the operator dashboard.

### 3. Create a Task

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Demo", "description": "Test task"}'
```

### 4. Run a Demo Agent

In another terminal with the virtual environment activated:

```bash
python scripts/local_runner.py \
  --base-url http://localhost:8000 \
  --auto-complete \
  --completion-notes "Verified locally"
```

Watch the dashboard update as work is leased and completed.

### 5. Two-Agent Workflow

For a more complete coordination example, see [docs/visuals/TWO_AGENT_WORKFLOW.md](docs/visuals/TWO_AGENT_WORKFLOW.md) and run:

```bash
python -m pytest server/tests/test_websocket_plan.py -v
```

This demonstrates the core pattern: Task A is ready, Agent 1 leases and completes it, Task B unlocks, Agent 2 leases Task B, and the dashboard receives live state updates.

## Documentation

- **[Architecture](docs/visuals/ARCHITECTURE_DIAGRAM.md)** — system components and data flow
- **[API Reference](docs/API.md)** — endpoint reference and examples
- **[Configuration](docs/configuration.md)** — environment variables and runtime settings
- **[Integration Guide](docs/ai-interface.md)** — how agents interact with Switchboard
- **[Documentation Index](docs/index.md)** — full navigation

## Validation

Use local validation as the source of truth for the checkout you are reviewing:

```bash
# Run the repository verification helper
python scripts/dev.py verify

# Run the full pytest suite directly
pytest -q

# Run strict browser UI tests when Playwright browsers are installed
SWITCHBOARD_STRICT_PLAYWRIGHT=1 pytest web/tests/test_ui.py -rA
```

The repository includes coverage for task lifecycle behavior, lease management, dependency unlocking, file storage, WebSocket plan updates, the Python client, and dashboard interactions. Exact counts and gate results can change as the project evolves, so release decisions should be based on the current branch's validation logs and audit notes.

## Security Model

Switchboard is designed for controlled agent-coordination environments. Before exposing it beyond localhost or a trusted network, review and configure:

| Area | Notes |
|---|---|
| Admin token | Set `SWITCHBOARD_ADMIN_TOKEN` for shared or exposed deployments. Local demos may run without it, but that should not be treated as production-safe. |
| Live-file storage | Keep `FILES_ROOT` inside the configured storage boundary and validate path-containment behavior in the target OS. |
| Upload limits | Set `SWITCHBOARD_MAX_LIVE_FILE_BYTES` to match your deployment profile. |
| Network exposure | Use TLS, a reverse proxy, and network access controls for shared deployments. |
| Secrets | Do not commit real tokens. Use placeholders in examples and environment-specific secret storage in deployments. |

See [SECURITY.md](SECURITY.md) and [docs/configuration.md](docs/configuration.md) for details.

## Configuration

Common environment variables:

```bash
# Database
DATABASE_URL=sqlite:///./switchboard.db

# Files
STORAGE_ROOT=./storage
FILES_ROOT=./storage/files

# Leasing
SWITCHBOARD_LEASE_SECONDS=60

# Security
SWITCHBOARD_ADMIN_TOKEN=replace-with-a-random-secret
SWITCHBOARD_MAX_LIVE_FILE_BYTES=10485760  # 10 MB

# Rate limiting
SWITCHBOARD_RATE_LIMIT_PER_MINUTE=100
```

## Local Development

```bash
# Run tests, lint, format checks, type checks, coverage, and security checks supported by the local environment
python scripts/dev.py verify

# Install pre-commit hooks
python scripts/dev.py bootstrap

# See available commands
python scripts/dev.py --help
```

## Visual Evidence

- **[System Architecture](docs/visuals/ARCHITECTURE_DIAGRAM.md)** — component diagram and data flow
- **[Two-Agent Workflow](docs/visuals/TWO_AGENT_WORKFLOW.md)** — sequence diagram for dependency unlocking
- **[Dashboard State](docs/visuals/DASHBOARD_STATE_EXAMPLE.md)** — how plan state evolves in real time

## Project Structure

```text
server/                    # FastAPI backend
├── api/                   # REST and WebSocket endpoints
├── application/           # Business logic
├── domain/                # Core task, lease, and dependency models
├── infrastructure/        # Persistence and adapters
├── middleware/            # Rate limiting, logging, observability
└── tests/                 # Server test coverage

client/python/             # Python client library and CLI
├── switchboard_client.py  # Low-level HTTP client
├── switchboard_cli.py     # Command-line interface
└── tests/                 # Client-side tests

web/                       # Operator dashboard
└── tests/                 # Browser UI tests

scripts/                   # Development and deployment helpers
├── run_uvicorn.py         # Start server
├── run_pytest.py          # Run tests
├── local_runner.py        # Demo agent
└── dev.py                 # Development CLI

docs/                      # Documentation
├── visuals/               # Architecture and workflow diagrams
├── API.md                 # Endpoint reference
├── architecture/          # Detailed system design
└── guides/                # Integration and operations guidance
```

## Current Status

- Core task coordination, leasing, dependency unlocking, Python client, and dashboard flows are implemented.
- Public-release readiness depends on the current branch's validation results, security review, documentation alignment, and repository settings.
- CodeQL, GitHub Secret Protection, and Push Protection may require public visibility or eligible licensing before activation.

## Governance

- [License](LICENSE) — Apache License 2.0
- [Security Policy](SECURITY.md) — vulnerability reporting and supported security posture
- [Contributing](CONTRIBUTING.md) — development guide
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Support Guide](docs/guides/support.md)

## Suggested Reviewer Path

1. **[Review Architecture](docs/visuals/ARCHITECTURE_DIAGRAM.md)** — understand components and data flow.
2. **[See Two-Agent Workflow](docs/visuals/TWO_AGENT_WORKFLOW.md)** — understand coordination behavior.
3. **Run the Quick Start** — observe the dashboard locally.
4. **[Review Security Controls](SECURITY.md)** — confirm the deployment posture matches your use case.
5. **[Run Validation](#validation)** — verify the current checkout before relying on it.

---

Questions? See the [Support Guide](docs/guides/support.md) or open an issue on GitHub.