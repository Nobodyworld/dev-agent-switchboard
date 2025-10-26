# Release Notes

## Upgrade Considerations
- Install the `pytest-cov` and `coverage` extras (now required to reproduce the documented coverage workflow).
- Regenerate virtual environments to pick up tightened lint/type tooling; `pip install -r server/requirements.txt && pip install -r client/python/requirements.txt` remains sufficient.
- Drop the legacy `FIXED_ENDPOINTS_REFERENCE.py` and `test_plan_endpoint_fixes.py` artifacts from downstream forks—they have been removed in favour of the live tests.
- Replace any imports of `server.interfaces` with the canonical Pydantic schemas in `server.schema`; the dataclass module has been removed.
- If you disable builtin extensions in production, set `SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS=0`; otherwise the builtin task
  metrics hook activates automatically.
- The Makefile now bootstraps a project-local `.venv` before running lint, test,
  or coverage targets. Prefer `make setup`/`make coverage` (or `scripts/dev.py
  bootstrap`) to ensure the same interpreter layout as CI.
- Install `pip-audit` (now listed in `server/requirements-dev.txt`) so
  `python scripts/dev.py verify` runs the same supply-chain scan as CI.

## Breaking Changes
- None. Interfaces and HTTP contracts remain unchanged.

## Operational Notes
- Diagnostics helpers cache requirement metadata; call
  `server.observability.diagnostics.clear_required_versions_cache()` after
  mutating dependency pins in a long-running process to refresh diagnostics
  output.
- `scripts/audit_metrics.py` collects coverage, complexity, and dependency depth metrics into `reports/system_metrics.json`; incorporate it into stewardship or CI reporting workflows.
- `/api/observability/telemetry` surfaces instrumentation status (logging,
  metrics, tracing, webhook) alongside the request ID header; update dashboards
  or agents to poll this endpoint before making assumptions about observability.
- `/api/settings.extensions` now includes `contract_version` and
  `contract_notes`; automation consuming this payload should ignore unrecognised
  keys to remain forward compatible.
- CLI helpers (`scripts/run_pytest.py` and `scripts/run_uvicorn.py`) now execute the Python entry points directly; any automation invoking these scripts should no longer rely on `subprocess` shell semantics.
- The default uvicorn host is now `127.0.0.1` to reduce accidental exposure; pass `--host 0.0.0.0` explicitly when remote access is required.
- Lint enforcement via Ruff is stricter. Run `ruff check` locally before pushing to avoid CI failures.
- `/api/settings` exposes `extensions` metadata (modules, builtin toggle, registered descriptors). Dashboards or agents that
  cache the payload should tolerate the new object.
- New developer CLI `scripts/dev.py` replaces ad-hoc release tooling; automation should call `python scripts/dev.py bump-version` when preparing a tagged release.
- Reloading extension settings now refreshes the runtime bundle so disabling builtin plugins or swapping modules is immediately
  reflected by `/api/settings` responses and broadcast metadata.
- `/health/live` and `/health/ready` now surface uptime, start timestamps, and
  deployment identifiers to aid incident response without changing success
  criteria.
- The builtin `webhook_notifier` activates automatically when
  `SWITCHBOARD_WEBHOOK_URL` is set; ensure downstream endpoints tolerate duplicate
  deliveries and log correlation IDs.

## Testing
- `pytest -q`
- `make coverage`
- `python scripts/dev.py coverage-gate --json reports/coverage.json --module server/extensions/loader.py=85 --module server/extensions/runtime.py=85 --module server/extensions/builtin/task_metrics.py=85 --module server/observability/diagnostics.py=80`
- `python scripts/dev.py verify --coverage-json reports/coverage.json`
