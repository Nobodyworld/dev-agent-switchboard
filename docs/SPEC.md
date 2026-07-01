# Switchboard Specification

_Last updated: 2025-10-31_

Switchboard is a FastAPI service that orchestrates human and automated agents
through a shared task plan, live file mirror, and observability surface. This
specification captures the authoritative repository structure, quality gates,
and operational expectations.

## Repository Snapshot

- **Primary stack:** Python 3.11, FastAPI, SQLAlchemy, Prometheus instrumentation.
- **Client tooling:** Python SDK and CLI (`client/python/`, `switchboard_cli.py`).
- **UI:** Static dashboard in [`web/`](../web/) served directly by FastAPI.
- **Persistence:** SQLAlchemy ORM with SQLite defaults for local development.
- **Task tracking:** [`TASKLIST.md`](TASKLIST.md) (single source of truth).
- **ExecPlans:** Maintained under [`.agent/PLANS.md`](../.agent/PLANS.md).

## Directory Layout

| Path | Purpose |
| --- | --- |
| [`server/`](../server/) | FastAPI routers, domain logic, observability stack, extension runtime. |
| [`client/`](../client/) | Client libraries for agents, including the packaged Python SDK. |
| [`web/`](../web/) | Operator dashboard HTML/CSS/JS and accompanying UI tests. |
| [`scripts/`](../scripts/) | Developer utilities (`dev.py`, coverage gates, local runner). |
| [`tests/`](../tests/) | Black-box tests for CLI, SDK, and configuration parsing. |
| [`docs/`](.) | Architecture references, guides, reports, and historical archives. |
| [`reports/`](../reports/) | Machine-generated metrics (coverage, complexity, performance). |
| [`ops/`](../ops/) | Deployment aides (Docker Compose, logging config, OpenTelemetry collector). |
| [`archive/`](../archive/) | Frozen patches and legacy task snapshots kept for provenance. |

Each directory now includes a `README.md` describing its scope and linking to
supporting references.

## Tooling & Quality Gates

- **Setup:** `python -m venv .venv && source .venv/bin/activate && pip install -r server/requirements-dev.txt`.
- **One-shot verification:** `python scripts/dev.py verify` mirrors CI (format,
  lint, type check, tests, security scan, coverage gate).
- **Individual commands:**
  - `make lint` → `ruff` static analysis.
  - `make typecheck` → `mypy` strict mode for critical modules.
  - `make test` or `pytest -q` for unit/integration tests.
  - `make security` for Bandit and dependency scanning.
  - `make coverage` to regenerate `reports/coverage.json` and enforce thresholds.
- **Client packaging:** `pip install -e .` exposes `switchboard_cli` entry points.

## Configuration & Environment

- Server configuration is sourced from environment variables defined in
  [`server/settings.py`](../server/settings.py). Rate limit, lease, and extension
  overrides are validated aggressively and cached for reuse.
- Operational manifests live in [`ops/`](../ops/) and are mirrored in
  [`docs/configuration.md`](configuration.md).
- Use `python scripts/dev.py verify` before committing to ensure configuration
  parsing tests pass with any new defaults.

## Documentation & Process

- Start with [`docs/README.md`](README.md) -> [`docs/index.md`](index.md)
  for curated navigation. [`docs/navigation-index.md`](navigation-index.md)
  retains the legacy map for archival completeness.
- Architectural deep dives: [`docs/architecture/`](architecture/).
- Automation & support playbooks: [`docs/guides/`](guides/).
- Reports & retrospectives: [`docs/reports/`](reports/).
- Historical context: [`docs/history/`](history/) and [`archive/`](../archive/).
- Update [`CHANGELOG.md`](../CHANGELOG.md) and [`RELEASE_NOTES.md`](RELEASE_NOTES.md)
  with user-visible changes.

## Planning & Governance

- All active work must be represented in [`TASKLIST.md`](TASKLIST.md) with a
  completion note when finished.
- Significant refactors or multi-step deliveries require an ExecPlan entry in
  [`.agent/PLANS.md`](../.agent/PLANS.md) kept in sync with the live Switchboard copy.
- Follow the conventions in [`STYLE-GUIDE.md`](STYLE-GUIDE.md) and ensure new
  modules include docstrings and type hints for non-trivial logic.

## Validation Checklist

Before shipping changes:

1. `python scripts/dev.py verify`
2. `pytest -q`
3. Regenerate metrics when behaviour shifts (`make coverage`, `python scripts/audit_metrics.py`).
4. Update documentation cross-links and the changelog.
5. Confirm directory READMEs accurately describe new artefacts.
