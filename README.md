# Switchboard

**Real-time agent coordination with dependency-aware leasing and trusted local execution.**

Switchboard is a reference implementation for coordinating multiple agents against a shared task graph. Agents can discover ready work, lease tasks, publish mutable reference files, and observe plan changes without each project needing its own orchestration service. The merged execution foundation also supports explicitly approved, outbound local work against operator-allowlisted repositories using exact-SHA disposable worktrees and immutable reviewed commands.

![Switchboard dashboard state demonstration](docs/assets/switchboard-dashboard.png)

## What It Demonstrates

- **Dependency-aware coordination** — tasks become available as prerequisites complete.
- **Lease-based ownership** — agents claim work with expiry and heartbeat semantics that reduce duplicate execution.
- **Trusted local execution** — approved exact-SHA work orders are claimed by an outbound local worker using fixed reviewed argv, read-only disposable worktrees, bounded output, cancellation, and cleanup.
- **Live state synchronization** — plan changes are broadcast to the dashboard and clients over WebSockets.
- **Live-file hosting** — agents can fetch mutable documents by URL; mutation endpoints can be protected with an admin token.
- **Operational visibility** — health, readiness, diagnostics, metrics hooks, structured logs, and rate limiting.

## Why It Matters

Autonomous coding agents, deterministic local workers, script runners, and human reviewers need a shared source of truth while work is in flight:

- a plan that changes as tasks complete;
- a queue that respects dependencies and ownership;
- an explicit approval and lease boundary for trusted local execution;
- a lightweight document surface for prompts, checklists, and runtime notes;
- a dashboard that exposes coordination state.

Switchboard provides that coordination layer as a small, inspectable application rather than a hosted production service.

## Quick Start

### 1. Set up the environment

```bash
# Clone and enter the repository
git clone https://github.com/Nobodyworld/dev-agent-switchboard.git
cd dev-agent-switchboard

# Create a Python 3.11+ virtual environment
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r server/requirements-dev.txt
```

### 2. Run the server

```bash
python scripts/run_uvicorn.py
```

Open [http://localhost:8000/](http://localhost:8000/) to view the operator dashboard.

### 3. Create a task

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Demo", "description": "Test task"}'
```

### 4. Run a demo agent

In another terminal with the virtual environment activated:

```bash
python scripts/local_runner.py \
  --base-url http://localhost:8000 \
  --auto-complete \
  --completion-notes "Verified locally"
```

Watch the dashboard update as work is leased and completed.

### 5. Review the two-agent flow

See [docs/visuals/TWO_AGENT_WORKFLOW.md](docs/visuals/TWO_AGENT_WORKFLOW.md), then run:

```bash
python -m pytest server/tests/test_websocket_plan.py -v
```

The scenario demonstrates Task A being leased and completed, Task B unlocking, a second agent leasing Task B, and the dashboard receiving live updates.

## Validation

Use the current checkout and protected workflow as the source of truth:

```bash
python scripts/dev.py verify
pytest -q
SWITCHBOARD_STRICT_PLAYWRIGHT=1 pytest web/tests/test_ui.py -rA
```

The protected GitHub Actions matrix covers:

- pinned pre-commit and repository policy checks;
- Ruff and Black formatting validation;
- strict Mypy type checking;
- full pytest execution;
- aggregate and configured module coverage gates;
- Bandit and dependency auditing;
- full-history Gitleaks scanning;
- documentation link validation;
- strict browser UI tests that fail when skipped.

Exact counts, coverage percentages, workflow identifiers, and environment limitations change as the repository evolves. They are intentionally recorded in active pull requests, living ExecPlans, the [public status page](docs/reports/status.md), and [PUBLIC_RELEASE_AUDIT.md](PUBLIC_RELEASE_AUDIT.md) rather than duplicated here as permanent claims.

Formal release still requires the Linux symlink-containment regression to execute without a skip against one selected release-candidate SHA, complete clean-clone and Docker evidence, and the owner-controlled release/settings review tracked in issues #95 and #104.

## Security Model

The public developer preview is intended for localhost or controlled trusted networks. Public repository visibility makes the source available for review; it does not make a running Switchboard instance safe for public hosting. Untrusted multi-tenant and direct internet-facing deployments are unsupported.

Before using Switchboard on a trusted shared network, review and configure:

| Area              | Guidance                                                                                                              |
| ----------------- | --------------------------------------------------------------------------------------------------------------------- |
| Admin token       | Set `SWITCHBOARD_ADMIN_TOKEN` for shared deployments. A local demo without a token is not production-safe.           |
| Live-file storage | Keep `FILES_ROOT` inside the intended storage boundary and validate containment on the target operating system.       |
| Upload limits     | Set `SWITCHBOARD_MAX_LIVE_FILE_BYTES` for the deployment profile.                                                     |
| Network exposure  | Keep the preview on localhost or a controlled trusted network; direct public-internet exposure is unsupported.        |
| Secrets           | Use environment-specific secret storage and never commit real tokens.                                                 |
| Dependency risk   | Run `pip-audit`, Dependabot, and the documented security gates against any release candidate.                         |

Common settings:

```bash
DATABASE_URL=sqlite:///./switchboard.db
STORAGE_ROOT=./storage
FILES_ROOT=./storage/files
SWITCHBOARD_LEASE_SECONDS=60
SWITCHBOARD_ADMIN_TOKEN=replace-with-a-random-secret
SWITCHBOARD_MAX_LIVE_FILE_BYTES=10485760
SWITCHBOARD_RATE_LIMIT_PER_MINUTE=100
```

See [SECURITY.md](SECURITY.md) and [docs/configuration.md](docs/configuration.md).

## Documentation

- **[Architecture](docs/visuals/ARCHITECTURE_DIAGRAM.md)** — components, data flow, and security boundaries.
- **[API Reference](docs/API.md)** — endpoints and examples.
- **[Configuration](docs/configuration.md)** — environment variables and runtime settings.
- **[Agent Integration](docs/ai-interface.md)** — how agents interact with Switchboard.
- **[Local Worker Operations](docs/operations/local-worker.md)** — trusted repository mapping, worker configuration, execution, evidence retention, and limitations.
- **[Public Status](docs/reports/status.md)** — current developer-preview posture and release boundaries.
- **[Two-Agent Workflow](docs/visuals/TWO_AGENT_WORKFLOW.md)** — dependency-unlock sequence.
- **[Documentation Index](docs/index.md)** — full navigation.

## Project Structure

```text
server/                    # FastAPI backend
├── api/                   # REST and WebSocket endpoints
├── application/           # Coordination services
├── domain/                # Task, lease, and dependency models
├── infrastructure/        # Persistence and adapters
├── middleware/            # Rate limiting, logging, observability
└── tests/                 # Server test coverage

client/python/             # Python client library and CLI
web/                       # Operator dashboard and browser tests
scripts/                   # Development, validation, and demo helpers
docs/                      # Architecture, API, integration, and operations docs
```

## Release Status

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

This classification distinguishes four separate decisions:

1. **Repository visibility:** the source may be publicly visible for inspection, evaluation, and contribution.
2. **Developer-preview availability:** developers may run the project locally or on a controlled trusted network.
3. **Release authorization:** no production release, version tag, or general-availability claim is authorized.
4. **Production deployment safety:** untrusted multi-tenant and internet-facing deployment remain unsupported.

Formal release authorization remains blocked until the Linux symlink-containment regression executes successfully against the selected release candidate, final clean-clone and Docker evidence is recorded, and the owner completes the release/settings review tracked in issues #95 and #104.

## Governance

- [Apache License 2.0](LICENSE)
- [Notice](NOTICE)
- [Security Policy](SECURITY.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Support Guide](docs/guides/support.md)

## Suggested Reviewer Path

1. Review the dashboard screenshot and [architecture diagram](docs/visuals/ARCHITECTURE_DIAGRAM.md).
2. Read the [two-agent workflow](docs/visuals/TWO_AGENT_WORKFLOW.md).
3. Review the [local worker operations guide](docs/operations/local-worker.md).
4. Run the quick start locally.
5. Review [SECURITY.md](SECURITY.md), the [public status page](docs/reports/status.md), and the [release audit](PUBLIC_RELEASE_AUDIT.md).
6. Inspect the task, lease, execution-worker, live-file, WebSocket, and browser tests.
