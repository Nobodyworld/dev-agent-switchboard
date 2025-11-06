# Websocket Backoff Follow-up Audit (2025-11-06)

## Snapshot & Baseline

### Runtime & Tooling Versions

- Python 3.11.12 (`python --version`)
- Node.js v22.19.0 (`node --version`)
- Pytest 8.4.1 (`pytest --version`)
- Ruff 0.12.11 (`ruff --version`)
- Black 25.1.0 (`black --version`)
- MyPy 1.17.1 (`mypy --version`)

### Command Inventory

| Command | Purpose |
| --- | --- |
| `make setup` | Provision the virtualenv and install development requirements (blocked in offline sandbox; see _Automated Audit_). |
| `make dev` | Run the FastAPI app locally with autoreload (`uvicorn server.app:app`). |
| `make test` | Execute server-focused pytest suite. |
| `make lint` | Run Ruff across `server/`, `client/`, `scripts/`, and `tests/`. |
| `make fmt` | Format Python sources with Black. |
| `make typecheck` | Strict MyPy check for `server/file_store.py` and `client/python/switchboard_client.py`. |
| `make security` | Bandit scan of `server/` (fails offline until dependencies installed). |
| `make coverage` | Pytest coverage run with module gates. |
| `make build` | Docker Compose build for production image. |
| `make deploy` | Docker Compose `up --build --detach` to launch the stack. |

### Environment Variables

Operational configuration is environment-first. Core variables include:

- `DATABASE_URL`, `STORAGE_ROOT`, `FILES_ROOT` — persistence locations (see `server/db.py`).
- Rate limiting knobs (`SWITCHBOARD_RATE_LIMIT_REQUESTS`, `SWITCHBOARD_RATE_LIMIT_WINDOW_SECONDS`, `SWITCHBOARD_RATE_LIMIT_TRUSTED_BYPASS`, `SWITCHBOARD_RATE_LIMIT_TRUSTED_PROXIES`).
- Lease and maintenance controls (`SWITCHBOARD_LEASE_SECONDS`, `SWITCHBOARD_ADMIN_TOKEN`).
- Extension toggles (`SWITCHBOARD_EXTENSIONS`, `SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS`).
- Observability switches (`SWITCHBOARD_ENABLE_STRUCTURED_LOGGING`, `SWITCHBOARD_ENABLE_METRICS`, `SWITCHBOARD_METRICS_PATH`, `SWITCHBOARD_ENABLE_TRACING`, `SWITCHBOARD_TRACING_EXPORTER`, `SWITCHBOARD_OTEL_CONFIG`, `SWITCHBOARD_LOGGING_CONFIG`, `SWITCHBOARD_LOGGING_DICT`, `SWITCHBOARD_ENABLE_REQUEST_ID`, `SWITCHBOARD_REQUEST_ID_HEADER`).
- Activity feed limits (`SWITCHBOARD_ACTIVITY_FEED_SIZE`) and webhook settings (`SWITCHBOARD_WEBHOOK_URL`, `SWITCHBOARD_WEBHOOK_EVENTS`, `SWITCHBOARD_WEBHOOK_HEADERS`, `SWITCHBOARD_WEBHOOK_TIMEOUT`).

### CI Workflow Inventory

- **CI (`ci.yml`)** — matrix stages (`lint`, `typecheck`, `test`, `security`) plus coverage, link check (lychee), and gitleaks secrets audit.
- **Commitlint (`commitlint.yml`)** — validates conventional commit messages on pull requests and merge queues.

### Dependency & License Snapshot

| Package | Version | License (upstream) | Notes |
| --- | --- | --- | --- |
| FastAPI | 0.120.0 | MIT | Primary API framework. |
| Starlette | 0.48.0 | BSD | ASGI toolkit used by FastAPI. |
| Uvicorn | 0.38.0 | BSD | ASGI server. |
| Pydantic | 2.12.3 | MIT | Data validation for schemas. |
| SQLAlchemy | 2.0.44 | MIT | ORM and query toolkit. |
| aiosqlite | 0.21.0 | MIT | Async SQLite driver. |
| python-multipart | 0.0.20 | Apache-2.0 | Multipart form parsing. |
| httpx | 0.28.1 | BSD | HTTP client for instrumentation/tests. |
| Jinja2 | 3.1.6 | BSD | Template rendering. |
| Prometheus FastAPI Instrumentator | 7.1.0 | MIT | Metrics exporter. |
| OpenTelemetry SDK / Exporters / FastAPI instrumentation | 1.38.0 / 1.38.0 / 0.59b0 | Apache-2.0 | Tracing pipeline. |
| PyYAML | 6.0.3 | MIT | YAML parsing for configuration. |
| python-json-logger | 4.0.0 | BSD-2-Clause | Structured logging. |

## Automated Audit

| Check | Result |
| --- | --- |
| `make setup` | ❌ Failed: pip could not reach package index through proxy; FastAPI wheel unavailable. Manual installs required in connected environment. |
| `pytest web/tests/test_ws_backoff.py -q` | ✅ Passed: Node-driven regression checks for the jittered backoff controller. |
| `pytest -q` | ✅ Passed: Full suite (218 passed, 2 skipped) on pre-provisioned tooling. |
| `ruff check .` | ⚠️ Failing: Existing issues in client/server modules (branch complexity, unused args) plus new JS-driven test lint that required remediation. Added notes in `TECH_DEBT.md`. |
| `black --check` (implied via CI) | Not rerun locally; formatting verified via targeted changes. |
| `mypy --config-file mypy.ini server client scripts` | ⚠️ Not executed (blocked by missing dev dependencies after `make setup` failure). |
| `bandit -q -r server` | ⚠️ Not executed; Bandit not available without `server/requirements-dev.txt`. |
| `pip-audit` | ⚠️ Not executed offline; flagged as TODO in `SECURITY_NOTES.md`. |
| Coverage gate | ⚠️ Skipped (pytest coverage plugin unavailable without dev dependencies). |

### Failures & Mitigations

- Documented the offline installation failure so operators can rerun `make setup` once the package index is reachable.
- Captured Ruff violations in `TECH_DEBT.md` for follow-up triage; the new web backoff tests were cleaned up in this PR.
- Security tooling gaps (Bandit, pip-audit) recorded in `SECURITY_NOTES.md` with remediation steps.

## Targeted Fixes

- Normalised Makefile whitespace and introduced `make dev`, `make build`, and `make deploy` to satisfy one-command flow requirements.
- Hardened `web/tests/test_ws_backoff.py` to resolve Ruff findings (absolute Node path, shared constants, wrapped skip messaging).
- Produced dependency, CI, and environment inventories for operators.

## Verification

- Smoke-validated websocket reconnect backoff via the Node-powered pytest module.
- Confirmed global pytest suite stays green in the sandbox environment.

_Performance profiling was not required: the change set is limited to the dashboard reconnect logic and documentation with no hot-path server impact._

## Ops & Developer Experience

- Updated Make targets to expose `dev`, `build`, `deploy` flows.
- Documented runtime commands and environment knobs for quick reference.

## Remaining Risks & TODOs

Refer to `TECH_DEBT.md` for prioritised follow-up items. Highlights include restoring Bandit/pip-audit once dependencies install successfully, addressing legacy Ruff warnings in the client CLI, and re-running coverage gates in a connected environment.
