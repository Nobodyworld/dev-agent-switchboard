# Switchboard Style Guide

_Last updated: October 31, 2025_

This guide defines the formatting, documentation, and collaboration conventions
for the Switchboard project. It complements the [SPEC](SPEC.md) and the
[documentation hub](docs/index.md).

## 0. Root Guarantees

- Never remove `README.md`, `SPEC.md`, or `TASKLIST.md` from the repository root.
- Keep `CHANGELOG.md`, `RELEASE_NOTES.md`, and `docs/` links in sync whenever
  behaviour changes.

## 1. Repository Organization

Canonical directories and expectations:

- `server/` — FastAPI application, domain model, extensions, observability.
- `client/` — Python SDK, CLI, and runtime configuration helpers.
- `web/` — static dashboard assets and DOM tests.
- `scripts/` — idempotent developer tooling (`dev.py`, coverage gates,
  local runner, automation scripts).
- `tests/` — black-box and integration tests driving CLI and configuration
  validation. Package-specific tests live in `server/tests/`.
- `docs/` — architecture deep dives, guides, reports, and history
  (see `docs/README.md`).
- `reports/` — machine-generated metrics (coverage, complexity, performance).
- `ops/` — deployment manifests (Docker Compose, logging, OpenTelemetry).
- `archive/` — frozen patches and task snapshots preserved for provenance.

Each directory ships a `README.md` describing scope, inputs, and primary
artifacts.

## 1.1 Tasks & Planning

- Track all work in `TASKLIST.md`; oldest items first, one line per task.
- Use completion notes (date, PR/reference, short summary) on checked items.
- Large efforts require an ExecPlan entry in `.agent/PLANS.md` kept in sync with
  the live Switchboard copy.

## 2. Python Standards

- Format with `black` (via `make fmt`) and lint with `ruff` (`make lint`).
- Type check critical modules using `mypy --strict`; new code should include
  type hints and docstrings describing parameters, return values, and side
  effects.
- Prefer explicit imports ordered stdlib → third-party → local.
- Raise descriptive errors and avoid silent failures; use structured logging via
  `logging` or the existing observability helpers.

## 3. Frontend Standards

- Keep `web/static/` assets modular; prefer ES modules and descriptive class
  names.
- Accessibility is mandatory: keyboard navigation, ARIA attributes, and colour
  contrast that satisfies WCAG 2.1 AA.
- Update or add DOM tests in `web/tests/` when UI behaviour changes.

## 4. Documentation

- Update relevant docs whenever behaviour or configuration changes. Start with
  `docs/README.md` and ensure `docs/index.md` or `docs/navigation-index.md`
  highlight new material.
- Cross-link major references (`SPEC.md`, `STYLE-GUIDE.md`, `TASKLIST.md`) from
  new documents where helpful.
- Use short front-matter summaries (title, description, tags) when adding files
  under `docs/` to keep navigation metadata coherent.

## 5. Testing & Quality Gates

- Run `python scripts/dev.py verify` before committing; it executes linting,
  type checking, tests, security scans, and coverage enforcement.
- Run `pytest -q` for quick iteration and `make coverage` when behaviour changes
  to refresh `reports/coverage.json`.
- Keep fast tests in `tests/` and scoped unit tests co-located under
  `server/tests/`.

## 6. Security & Compliance

- Never commit secrets. Use `.env.example` patterns and update `ops/` manifests
  as needed.
- Run `make security` (Bandit and dependency scanning) for code touching
  sensitive areas.
- Validate extension module overrides using the helpers in `server/settings.py`
  and document any new environment variables in `docs/configuration.md`.

## 7. Collaboration Process

- Conventional Commits (`type(scope?): message`) for all commits.
- Small, reviewable pull requests with clear summaries and updated changelog.
- Respond to review feedback promptly; capture significant deviations in
  `.agent/PLANS.md` or `docs/history/` as appropriate.

## 8. Continuous Improvement

- Monitor coverage thresholds enforced by `scripts/dev.py coverage-gate` and
  address regressions immediately.
- Update `reports/` metrics (`python scripts/audit_metrics.py`) after major
  refactors.
- Keep directory `README.md` files accurate as the structure evolves to reduce
  onboarding friction.
