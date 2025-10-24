# Codex Repo Perfection Chain — Step 1: Comprehend & Map

## Repository Purpose & Domain
- **Mission:** Switchboard orchestrates AI and human agents through a FastAPI router that manages task plans, leases, and live documentation mirrors so operators can coordinate complex workflows in real time.
- **Primary Users:** Automation agents integrating via HTTP/WebSocket, operators monitoring plans through the bundled UI, and developers extending the orchestration service or Python client toolkit.

## Architecture Overview
- **Entry Points:**
  - `server/app.py` wires FastAPI routes, WebSocket broadcasts, static UI hosting, and startup hooks (database schema creation, file storage setup).
  - `switchboard_cli.py` and `client/python/switchboard_cli.py` expose CLI tooling for local task management and agent emulation.
  - `web/` contains the HTMX-powered admin interface served by the API.
- **Domain & Application Layers:**
  - `server/domain/` defines immutable records (tasks, agents, leases) plus policies (`task_status.py`, `application/exceptions.py`).
  - `server/application/task_service.py` orchestrates task lifecycle operations while enforcing dependency and lease policies.
  - `server/infrastructure/repositories.py` implements persistence adapters backed by SQLAlchemy models (`server/models.py`) and async SQLite (`server/db.py`).
- **Cross-Cutting Concerns:**
  - Middleware & rate limiting live in `server/middleware/` and `server/settings.py`.
  - Observability hooks are centralized under `server/instrumentation/` (logging, metrics, tracing) and configured in `ops/` manifests for local deployments.
  - ExecPlan registry and live file mirroring are handled via `server/execplan_registry.py` and `server/file_store.py`, exposing `/live` endpoints plus plan metadata.
- **Client Toolkit:** The Python package in `client/python/` provides `SwitchboardClient`, CLI commands, and usage examples/tests; `tests/` at repository root covers CLI and client shims.

## Data Flow & Execution Model
1. **Task Creation:** Requests POST through `/api/tasks` → `TaskService.create_task` validates dependencies → SQLAlchemy repositories persist tasks and dependency edges.
2. **Task Leasing:** Agents call `/api/tasks/checkout` → `TaskService.checkout` applies availability policy (dependency completion, lease expiry, in-progress limits) → leases saved via `LeaseRepository` with deadlines enforced by `LeasePolicy`.
3. **Heartbeat & Completion:** `/api/tasks/{id}/heartbeat|complete|abandon` → `TaskService` verifies lease ownership and timeouts → updates statuses, notes, and plan versions → WebSocket broadcaster pushes plan deltas via `PlanBroadcast` logic.
4. **Live Files & ExecPlans:** Uploads hit `/api/files/{path}` → `file_store.put_file` writes to disk and refreshes ETag metadata → clients retrieve via `/live/<path>` while `execplan_registry` indexes `.agent/PLANS.md` for discoverability.
5. **UI Delivery:** Static assets under `web/static` and Jinja templates render dashboards that subscribe to `/ws/plan` for live updates.

## Key Features & Modules
- **Plan & Task Lifecycle:** `server/task_logic.py`, `server/application/`, `server/domain/`.
- **Agent Management:** `server/domain/agents.py`, endpoints for registration/lease heartbeats.
- **Rate Limiting & Leases:** `server/middleware/rate_limit.py`, `server/settings.py`, `server/task_status.py`.
- **Observability:** Logging/tracing via OpenTelemetry exporters (`prometheus-fastapi-instrumentator`, `opentelemetry-*`), plus `/health/live|ready` endpoints defined in `server/app.py` & `server/schema.py`.
- **Client Ergonomics:** `switchboard_client.py` (requests-based HTTP client with resilience) and `scripts/local_runner.py` for demo agent loops.
- **Testing Harness:** `server/tests/` for API/integration layers, `tests/` for CLI/client behavior; `Makefile` orchestrates lint/test targets.

## Dependency Snapshot
- **Backend:** FastAPI, Starlette, SQLAlchemy 2.x with async SQLite, Pydantic v2, httpx for internal calls, Jinja2 for templating.
- **Observability:** `prometheus-fastapi-instrumentator`, OpenTelemetry SDK + OTLP exporter, Python JSON logger.
- **Client:** Requests-based interactions (via standard library + third-party) packaged for distribution (`client/python/pyproject.toml`).
- **Tooling:** Ruff, Black, mypy; CI via GitHub workflows (`Makefile`, `ops/` config, `mypy.ini`).

## Documentation Status
- Comprehensive top-level guides: `README.md`, `ARCHITECTURE.md`, `docs/index.md`, and status reports (`REPORTS/*.md`).
- Documentation portal uses YAML front matter and navigation metadata (`docs/_meta/navigation.yaml`).
- Detailed API references (`docs/AI_INTERFACE.md`, `docs/message-schema.md`), testing report, and TODO backlog maintained in `docs/TODO-ISSUES.md`.
- Additional operational docs: `SUPPORT.md`, `STATUS.md`, `PROJECT_STATUS.md`, `IMPLEMENTATION_NOTES.md`.

## Current Pain Points & TODOs
- **Runtime Migration:** `server/app.py` performs an inline schema migration for `completed_notes`; needs formal Alembic revision to eliminate startup DDL.
- **Security Hardening:** CORS currently allows all origins; production deployment must restrict once domains finalize.
- **WebSocket Monitoring:** TODO to record connection metadata and simulate slow consumers (`server/app.py`, `server/tests/test_plan_broadcaster_unit.py`).
- **Repository Tests:** Legacy tests rely on `asyncio.run` and shared filesystem state; TODOs indicate migration to pytest-asyncio and temp directories.
- **UI Responsiveness:** `web/static/styles.css` notes mobile layout TODO; `web/static/app.js` highlights planned performance/backoff improvements.
- **Backlog Items:** Queue prioritization, Prometheus health metrics, and improved runner abandonment workflow remain open in `docs/TODO-ISSUES.md`.

## Quality & Operations Snapshot
- **Testing:** `Makefile` includes lint/test targets; root `tests/` cover client/CLI while `server/tests/` exercise domain logic (pending modernization per TODOs).
- **Deployment:** `ops/docker-compose.yml`, `ops/logging.ini`, and `ops/otel.yaml` demonstrate local orchestration with observability stacks.
- **Configuration:** `server/settings.py` centralizes rate-limit/lease settings; `switchboard_client.py` exposes configuration for base URL, agent ID, and timeouts.
- **Live Artifacts:** `.agent/PLANS.md` and AGENTS instructions enforce ExecPlan workflows for complex contributions.

## Immediate Opportunities
- Prioritize schema migration tooling and rate-limit tightening to reduce runtime risk.
- Invest in async-native tests and WebSocket backpressure simulations to harden concurrency behavior.
- Produce missing docs (UI customization, deployment playbooks, automation examples) flagged in `docs/PORTAL_STATUS.md` to close onboarding gaps.
