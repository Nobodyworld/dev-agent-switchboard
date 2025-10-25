# Changelog

## Unreleased

### Added
- Extension runtime under `server/extensions/` with builtin Prometheus task
  metrics hook and documentation in `EXTENSION_GUIDE.md`.
- `/api/settings` now surfaces extension configuration metadata (modules,
  builtin toggle, registered descriptors) for operators and agents.
- Developer CLI `scripts/dev.py` providing `bootstrap`, `coverage-gate`, and
  `bump-version` subcommands used by the Makefile and CI pipeline.
- `server/observability/runtime.py` captures process uptime, deployment
  metadata, and powers enriched health responses.
- Architecture, automation, and incident response documentation (`ARCHITECTURE_OVERVIEW.md`,
  `AUTOMATION.md`, `docs/incident-response.md`).
- Extension loader regression tests exercise explicit module loading,
  missing-registrar warnings, and error handling to backstop the new coverage
  thresholds.
- `server/interfaces.py` and `server/application/task_service.py` define immutable queue, task, and agent interfaces powering the checkout workflow.
- `/health/live` and `/health/ready` endpoints expose liveness and readiness probes via the new `HealthStatus` schema.
- `scripts/local_runner.py` provides a reference agent loop that registers, heartbeats, and optionally completes tasks.
- Documentation hub at `docs/index.md`, message schema reference, failure modes guide, and TODO backlog enumerating follow-up work.
- `/api/settings` endpoint exposing rate limit and lease configuration for operators and clients.
- Python CLI now fetches server settings and adjusts heartbeat intervals that would outlive the lease duration.
- CLI runtime summary output with accompanying [docs/cli-runtime.md](docs/cli-runtime.md) walkthrough plus the dependency audit in [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).
- Hardened developer helper scripts: `scripts/run_pytest.py` now shells directly into pytest, while `scripts/run_uvicorn.py` starts uvicorn via the library API and binds to loopback by default for safer local testing.
- Coverage workflow captured in `coverage.txt` to document current package-level coverage baselines.

### Changed
- `TaskService` emits lifecycle events to extension bundles so plugins can react
  to checkouts, completions, and task mutations without altering core logic.
- Health endpoints now include uptime, start timestamps, and process metadata to
  simplify diagnostics without breaking existing probes.
- CI adds a dedicated coverage job enforcing ≥85% coverage on the extension
  modules via `scripts/dev.py coverage-gate` (mirrored by `make coverage`).
- Makefile quality targets bootstrap a project-local virtual environment before
  executing linting, testing, or coverage so local runs mirror CI dependency
  resolution.
- README now introduces Switchboard via What/Why/How framing, highlights the local runner, and documents new health probes.
- Module docstrings across `server/` and the Python client follow NumPy style for consistent parameter/return documentation.
- Existing `docs/architecture.md` expanded with application/service context, while `docs/INDEX.md` links to the new documentation hub.
- License replaced with the Switchboard Proprietary notice reflecting the project's closed-source status.
- Lease duration parsing raises clearer "positive integer" errors and is validated during FastAPI startup, logging the active configuration.
- Settings caching now exposes an aggregated bundle so `/api/settings` and startup logging read a single coherent snapshot while cache reloads keep the views in sync.
- `/api/settings` reload helpers now refresh the extension runtime bundle so
  builtin toggles and module overrides take effect immediately in tests and in
  production environments.
- Python CLI surfaces warnings when server settings are missing or invalid and honours per-operation timeouts for `/api/settings` requests.
- `switchboard-cli run` now relies on the `SwitchboardClient` context manager and prints a tabular runtime configuration before starting the interactive loop.
- Task repository adapters batch dependency lookups and power new `TaskService`-focused tests that cover checkout, completion, and abandon flows without API indirection.
- Server modules now use absolute imports, typed set conversions, and explicit constants throughout tests to satisfy strict Ruff rules and improve readability.
- Release documentation expanded with `RELEASE_NOTES.md` to call out operator-facing upgrade guidance alongside the changelog.

### Fixed
- Restored missing imports in `server/tests/conftest.py` so database reset fixtures execute reliably during test runs.
- Removed stale reference artifacts in favour of the live test suite and addressed lint violations across CLI, test, and instrumentation code (magic numbers, nested context managers, hard-coded tokens).
- Resolved stale extension metadata when disabling builtin plugins by reloading
  the runtime bundle alongside settings cache refreshes.

## 2024-10-19 — Adaptive Perfection Update

### Added
- `REPORTS/000_CONTEXT.md`, `001_DIAGNOSIS.md`, and `002_VERIFICATION.md` capture environment, diagnostic, and testing details.
- `ARCHITECTURE.md` overview and `docs/AI_INTERFACE.md` describing agent integration points.
- `.env.example` and `LICENSE` to document configuration defaults and licensing terms.
- `tests/conftest.py` to ensure the project root is importable during pytest collection.
- `tests/test_settings_validation.py` covering rate limit configuration parsing.

### Changed
- Hardened `server/schema.TaskIn`/`TaskUpdate` with length constraints and metadata.
- Raised explicit `RateLimitConfigurationError` for invalid rate limit environment variables and updated associated tests.
- Replaced wildcard exports in `switchboard_cli.py` with explicit bindings.
- Enhanced README with configuration guidance referencing new settings validation.

### Fixed
- Prevented silent fallback when rate limit environment variables are invalid.
