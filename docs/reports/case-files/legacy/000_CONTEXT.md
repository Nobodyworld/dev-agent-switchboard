# Stage 1 — Environment & Context Detection

## Languages & Frameworks

- **Python 3.11+** — primary language for API (`server/`) and client libraries (`client/python/`).
- **FastAPI + Starlette** — REST + WebSocket service stack (`server/app.py`).
- **SQLAlchemy + aiosqlite** — data persistence layer for tasks (`server/models.py`, `server/db.py`).
- **HTMX + Tailwind CSS** — static admin UI served from `web/` referencing CDN builds (`web/index.html`).
- **JavaScript (ES module)** — lightweight client logic in `web/static/app.js`.

## Dependency & Build Tooling

- **pip/requirements** — runtime dependencies captured in `server/requirements.txt`; dev extras via `server/requirements-dev.txt`.
- **Makefile** — convenience targets for setup, run, lint, fmt, typecheck, tests, security, QA, and Docker compose.
- **pytest** — primary test runner (see `scripts/run_pytest.py`, `Makefile test`).
- **black**, **ruff**, **mypy**, **bandit** — formatting, linting, typing, and security tooling defined in dev requirements.
- **Playwright** (optional) — UI testing dependency listed in dev requirements.

## Repository Layout

- `server/` — FastAPI application, task logic, database models, instrumentation, and settings.
- `client/python/` — Python SDK and CLI utilities for agents; `switchboard_client.py` top-level shim.
- `web/` — Static admin UI assets (HTML, JS, CSS).
- `tests/` and `client/python/tests/` — Test suites for server and client components.
- `docs/` — Existing architecture and operational documentation.
- `scripts/` — Helper scripts for running the API, pytest, and plan publishing.
- `.agent/` — Agent-specific guidance and ExecPlan templates.
- `ops/` — Deployment assets (Docker Compose, etc.).

## Conventions & Configuration

- **Formatting** — `black` for Python, with `fmt` target scoping `server` and `client/python`.
- **Linting** — `ruff` configured via Makefile (`ruff check .`).
- **Typing** — Strict `mypy` checks for key modules (per Makefile `typecheck`).
- **Security** — `bandit` scan on `server/` directory.
- **CI/CD** — `.github/workflows/ci.yml` mirrors the Makefile gates, running tests and optional lint/type/format steps under GitHub Actions.
- **Docs** — README references quickstart, testing, and CI instructions; `docs/architecture.md` describes system layout.

## Notable Scripts & Entry Points

- `scripts/run_uvicorn.py` — development server runner.
- `scripts/run_pytest.py` — orchestrates pytest execution.
- `switchboard_cli.py` and `client/python/switchboard_cli.py` — CLI entry points for agents.
- `server/app.py` — ASGI entry point for FastAPI application.
