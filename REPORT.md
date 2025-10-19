# Switchboard Repo Intelligence Report

_Last updated: 2025-02-14_

## System Overview

| Layer | Responsibilities | Key Modules |
| --- | --- | --- |
| **API Server (FastAPI)** | Task lifecycle management (register, checkout, heartbeat, complete/abandon), plan version broadcasting over WebSocket, file uploads, settings + instrumentation bootstrap | `server/app.py`, `server/task_logic.py`, `server/models.py`, `server/schema.py`, `server/file_store.py`, `server/instrumentation/` |
| **Persistence** | Async SQLAlchemy engine + Alembic migrations, lightweight runtime DDL safety checks, SQLite storage (default) | `server/db.py`, `server/migrations/`, `server/settings.py` |
| **Rate Limiting & Middleware** | Request throttling with cached settings, correlation ID/logging hooks | `server/middleware/`, `server/settings.py`, `server/instrumentation/logging.py` |
| **ExecPlan Registry** | Serves historical plans and registry index for UI consumption | `server/execplan_registry.py`, `docs/execplans/` |
| **Static Operator UI** | HTMX-based dashboard rendered from templates, consumes REST + WebSocket APIs | `web/index.html`, `web/static/`, served via `server/app.py` |
| **Python Client SDK** | Requests-based wrapper for agent operations, retries/heartbeats, CLI orchestrator | `client/python/switchboard_client.py`, `client/python/switchboard_cli.py`, root shims `switchboard_client.py` & `switchboard_cli.py` |
| **Tooling & Ops** | Makefile targets, docker-compose environment, telemetry configs | `Makefile`, `ops/docker-compose.yml`, `ops/otel.yaml` |
| **Tests** | Pytest suites for client SDK/CLI and selected server components | `client/python/tests/`, `tests/`, `server/tests/` |

### Data Flows

1. Agents register via `POST /api/agents`; responses include lease heartbeat cadence and plan version metadata.
2. Agents poll for work via `POST /api/tasks/checkout`; server consults `tasks`/`leases` tables, returning the next available task.
3. Long-running agents maintain leases with `POST /api/tasks/{id}/heartbeat`; stale leases are pruned in `task_logic.py`.
4. Task completions trigger `plan_version` increments and broadcast messages through `PlanBroadcaster` WebSocket hub to connected dashboards.
5. File uploads stream to disk under `file_store.py` utilities, then are referenced in plan/task metadata.
6. Operator UI loads via `GET /` (Jinja template) and uses HTMX fragments plus `/ws/plan` WebSocket for live updates.
7. CLI tooling wraps the client SDK, providing interactive prompts and heartbeat threads for human operators.

### Public Surfaces

- **REST API**: `/api/agents`, `/api/tasks` (CRUD + checkout/heartbeat), `/api/status`, `/api/files`, `/api/plan`.
- **WebSocket**: `/ws/plan` for plan snapshot/version push notifications.
- **Static UI**: served at `/` with supporting `/static/*` assets.
- **CLI Entrypoints**: `python -m client.python.switchboard_cli` or `switchboard_cli.py` shim for backwards compatibility.
- **Automation Hooks**: `scripts/run_pytest.py`, Makefile targets (`make run`, `make test`, `make qa`).

### Background Jobs & Cron

- No persistent workers; lease cleanup and plan versioning are handled inline with API requests. Opportunity to extract into background scheduler if scale grows.

## Tech Stack & Dependency Map

- **Languages**: Python 3.11+, HTML/Tailwind/HTMX for UI, YAML/TOML configs.
- **Frameworks**: FastAPI + Starlette, SQLAlchemy (async), Jinja2, Requests, Pytest, Playwright (optional), Prometheus + OpenTelemetry instrumentation.
- **Tooling**: Ruff, Black, Mypy (configured but not strict), Makefile, Docker Compose, GitHub Actions (basic pipeline), pre-commit (limited hooks).

### Dependency Graph (High Level)

```
Client CLI ─┐
            ├─> client/python/switchboard_client.py ──> REST API (`server/app.py`)
Client SDK ─┘                                            │
                                                     SQLAlchemy ORM ──> SQLite (default)
                                                     │
                                                     ├─> File Store (`server/file_store.py`) ──> Local disk
                                                     ├─> ExecPlan Registry (`server/execplan_registry.py`) ──> docs/execplans
                                                     └─> Instrumentation (`server/instrumentation/`) ──> logging/prometheus/OTel

Operator UI (web/) ──> FastAPI template rendering + WebSocket broadcaster
```

### Hotspots & Potential Dead Code

- `server/app.py` is ~800 lines and mixes routing, broadcasting, templating, and runtime migrations — prime candidate for modularization.
- `RateLimitMiddleware` caches settings globally; combined with mutable environment overrides, this can leak state across tests.
- `server/app.py` performs ad-hoc schema migration (`ALTER TABLE tasks ADD COLUMN completed_notes`) on startup despite Alembic migrations existing — indicates drift between runtime and migrations.
- Root shims `switchboard_client.py`/`switchboard_cli.py` duplicate exports from `client/python/` package; confirm if external users still rely on them (possible deprecation path).
- `REPORTS/` directory appears archival; contents are not referenced by code.
- Some Alembic migrations may be unused because runtime DDL still compensates; need audit.

## Risks & Quick Wins

| Area | Risk | Quick Win |
| --- | --- | --- |
| **Governance** | Missing CODEOWNERS, CODE_OF_CONDUCT, SECURITY policy; inconsistent contributor guidance. | Introduce governance docs + PR templates to codify expectations. |
| **CI/CD** | Existing workflows limited; lack of matrix builds, caching, or strict enforcement. | Build GitHub Actions pipeline running lint/format/type/test with caching + artifact uploads. |
| **Typing** | Mypy config exists but not strict; optional imports bypass type checking. | Enable strict mode incrementally with stub packages + targeted suppressions. |
| **Security** | No SBOM/secret scanning; runtime allows arbitrary file uploads without size guard. | Add gitleaks/trivy pre-commit + CI, implement upload size/config validation. |
| **DX** | Setup steps scattered; no first-hour guide or bootstrap script. | Provide `make bootstrap`/`just` targets and quick-start documentation. |
| **Observability** | Logging/tracing modules exist but inconsistent usage; metrics not enforced. | Standardize structured logging + ensure metrics/traces registered in FastAPI startup tests. |

## Top 10 Opportunities by ROI

1. **Governance & Automation Baseline** – Add CODEOWNERS, CONTRIBUTING, SECURITY, PR templates, Renovate, commitlint, EditorConfig; unlock consistent contributions. _(Impact: High, Effort: Low)_
2. **CI/CD Hardening** – Replace existing workflow with cached multi-stage pipeline (lint/type/test/build), add status checks. _(Impact: High, Effort: Medium)_
3. **Strict Typing & Lint Enforcement** – Turn on `mypy --strict`, `ruff --select ALL`, add type hints; prevents regressions. _(Impact: High, Effort: Medium)_
4. **Runtime Migration Cleanup** – Remove startup DDL, rely on Alembic migrations with migration tests. _(Impact: Medium, Effort: Low)_
5. **Configuration Validation** – Introduce Pydantic `BaseSettings` with schema validation + `.env.example`. _(Impact: Medium, Effort: Low)_
6. **Secret & Dependency Scanning** – Add gitleaks, pip-audit/uv pip compile, SBOM via Syft/CycloneDX. _(Impact: High, Effort: Medium)_
7. **Observability Instrumentation** – Adopt OpenTelemetry context propagation, Prometheus metrics, log correlation IDs. _(Impact: Medium, Effort: Medium)_
8. **Test Pyramid Expansion** – Add integration tests for WebSocket broadcaster + CLI e2e under docker-compose with ephemeral DB. _(Impact: High, Effort: Medium)_
9. **Performance Guardrails** – Add request timeouts, DB indices on `leases`, caching plan snapshots, and profiling scripts. _(Impact: Medium, Effort: Medium)_
10. **DX Improvements** – Create `make dev`/`make test` orchestrations, first-hour guide, troubleshooting doc, align formatting (Black/Ruff + Prettier for web). _(Impact: Medium, Effort: Low)_

## Additional Notes

- README, ARCHITECTURE.md, and PROJECT_STATUS.md contain overlapping narratives; align them with PLAN.md outputs to avoid drift.
- Ops manifests (otel.yaml, docker-compose) lack automation hooks; consider Helm/Kustomize or Terraform integration in later milestones.
- Maintain STATUS.md after each PR per directive to signal progress and open questions.
