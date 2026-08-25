# Switchboard

**Real-time agent coordination with dependency-aware leasing, trusted local execution, and compact exact-SHA evidence.**

Switchboard is a reference implementation for coordinating multiple agents against a shared task graph. Agents can discover ready work, lease tasks, publish mutable reference files, and observe plan changes without each project needing its own orchestration service. The merged execution foundation also supports explicitly approved, outbound local work against operator-allowlisted repositories using exact-SHA disposable worktrees and immutable reviewed commands. Completed validation runs retain full logs locally while exposing strict compact evidence, hashes, parsed results, cleanup state, and deterministic fingerprints through the control plane.

![Switchboard dashboard state demonstration](docs/assets/switchboard-dashboard.png)

## What It Demonstrates

- **Dependency-aware coordination** — tasks become available as prerequisites complete.
- **Lease-based ownership** — agents claim work with expiry and heartbeat semantics that reduce duplicate execution.
- **Trusted local execution** — approved exact-SHA work orders are claimed by an outbound local worker using fixed reviewed argv, policy-governed disposable worktrees, bounded output, cancellation, and cleanup. Repository write prohibition is a cooperative trust and integrity-detection boundary, not an OS sandbox; live external targets require a least-privilege isolated worker host.
- **Compact validation evidence** — `validate-switchboard@1` records strict step outcomes, parsed test/coverage/security summaries, dependency-lock hashes, retained artifact hashes, and a deterministic fingerprint without returning full local logs.
- **Source-controlled workload factory** — four reviewed public catalog entries include the legacy Switchboard and Modular Accounting contracts plus `validate-zscripts@1` and `validate-industry-resilience@1`; profiles are compiled from typed repository source, never uploaded or target-authored configuration.
- **Validation Broker workspace** — operators can configure local-worker routing, resolve a GitHub pull request to an exact head, approve and queue it, distinguish fresh execution from exact reuse, publish current or stale evidence, and inspect bounded history without assembling API calls by hand.
- **Live state synchronization** — plan changes are broadcast to the dashboard and clients over WebSockets.
- **Live-file hosting** — agents can fetch mutable documents by URL; mutation endpoints can be protected with an admin token.
- **Operational visibility** — health, readiness, diagnostics, metrics hooks, structured logs, and rate limiting.

## Why It Matters

Autonomous coding agents, deterministic local workers, script runners, and human reviewers need a shared source of truth while work is in flight:

- a plan that changes as tasks complete;
- a queue that respects dependencies and ownership;
- an explicit approval and lease boundary for trusted local execution;
- compact proof of exactly what commit, manifest, environment, and dependency inputs were validated;
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

The **Validation Broker** workspace uses the same optional admin-token boundary as
the execution APIs. Its comparison units are operator-authored routing values,
not currency, provider credits, or measured savings. See the
[command-center operations guide](docs/operations/validation-command-center.md)
for the end-to-end workflow and trust boundaries.

### 3. Validate an exact source revision

For trusted deterministic validation, keep the server running, create the
operator-owned worker configuration described in the
[local-worker operations guide](docs/operations/local-worker.md), and start the
outbound worker from a second repository-root terminal:

```bash
python -m scripts.local_worker --config /operator/path/local-worker.json
```

Open the dashboard's **Validation Broker**, select an allowlisted repository and
the immutable reviewed manifest (for this repository,
`validate-switchboard@1`), enter the exact full source SHA, review routing and
policy, then explicitly approve and queue the request. The worker mapping must
point to an operator-approved clean canonical checkout that already contains the
exact commit. A fresh run remains the default; `allow_exact` may reuse retained
evidence only after same-worker identity, ownership, expiry, containment, size,
and SHA-256 verification. Approval and repository mapping are trust decisions,
not setup steps to automate.

### 4. Create a task

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Demo", "description": "Test task"}'
```

### 5. Run a demo agent

In another terminal with the virtual environment activated:

```bash
python scripts/local_runner.py \
  --base-url http://localhost:8000 \
  --auto-complete \
  --completion-notes "Verified locally"
```

Watch the dashboard update as work is leased and completed.

### 6. Review the two-agent flow

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
- strict browser UI tests that fail when skipped;
- isolated Python 3.11 / Node 24.12.0 / pnpm 10.18.1 Zscripts and Python 3.13
  Industry Resilience synthetic real-worker acceptances, each guarded as exactly
  one passing JUnit case with no skip, failure, or error.

Those hosted acceptance jobs execute committed synthetic fixtures inside this
repository only. They do not clone, execute, publish to, or retain artifacts
from either external target repository. Live dogfood remains an operator-owned
local exact-SHA activity with its own source and authorization preconditions.

Exact counts, coverage percentages, workflow identifiers, and environment limitations change as the repository evolves. They are intentionally recorded in active pull requests, living ExecPlans, the [public status page](docs/reports/status.md), and [PUBLIC_RELEASE_AUDIT.md](PUBLIC_RELEASE_AUDIT.md) rather than duplicated here as permanent claims.

Formal release still requires the Linux symlink-containment regression to execute without a skip against one selected release-candidate SHA, complete clean-clone and Docker evidence, and the owner-controlled release/settings review tracked in issues #95 and #104.

## Security Model

The public developer preview is intended for localhost or controlled trusted networks. Public repository visibility makes the source available for review; it does not make a running Switchboard instance safe for public hosting. Untrusted multi-tenant and direct internet-facing deployments are unsupported.

Trusted external workload profiles are reviewed Python source under
`server/execution/workload_profiles.py`. Their fixed argv, runtime requirements,
result-affecting inputs, retained-artifact limits, parsers, and deterministic
exclusions are digest-bound. The public API and dashboard expose only safe
identity and readiness metadata; they never expose a canonical checkout path,
command argv, environment value, full log, or artifact bytes.

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
- **[API Reference](docs/API.md)** — endpoints and examples, including compact execution evidence.
- **[Configuration](docs/configuration.md)** — environment variables and runtime settings.
- **[Agent Integration](docs/ai-interface.md)** — how agents interact with Switchboard.
- **[Local Worker Operations](docs/operations/local-worker.md)** — trusted repository mapping, worker configuration, execution, evidence retention, and limitations.
- **[Trusted Workload Onboarding](docs/operations/trusted-workload-onboarding.md)** — reviewed catalog entries, fixed manifests, worker mapping, and acceptance evidence.
- **[Validation Command Center](docs/operations/validation-command-center.md)** — browser workflow, bounded projections, exact-reuse metrics, and publication controls.
- **[Public Status](docs/reports/status.md)** — current developer-preview posture and release boundaries.
- **[Project Ruleset](PROJECT_RULESET.md)** — stable governance, safety, validation, and delivery rules.
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

The existing `v0.1.0-preview.1` tag is a historical developer-preview
checkpoint. It predates current `main` and the merged execution-broker,
exact-reuse, routing, Validation Broker, and workload-factory capabilities; it
is not current-main release evidence or production authorization.

## Governance

- [Apache License 2.0](LICENSE)
- [Notice](NOTICE)
- [Security Policy](SECURITY.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Support Guide](docs/guides/support.md)
- [Project Ruleset](PROJECT_RULESET.md)

## Suggested Reviewer Path

1. Review the dashboard screenshot and [architecture diagram](docs/visuals/ARCHITECTURE_DIAGRAM.md).
2. Read the [two-agent workflow](docs/visuals/TWO_AGENT_WORKFLOW.md).
3. Review the [local worker operations guide](docs/operations/local-worker.md).
4. Review the compact execution/evidence endpoints in [docs/API.md](docs/API.md).
5. Run the quick start locally.
6. Review [SECURITY.md](SECURITY.md), the [public status page](docs/reports/status.md), and the [release audit](PUBLIC_RELEASE_AUDIT.md).
7. Inspect the task, lease, execution-worker, evidence, live-file, WebSocket, and browser tests.
