# Changelog

## Unreleased

### Added
- Regression tests covering task analytics ready/blocked calculations and
  missing dependency detection to guard the new `/api/tasks/analytics` route.
- JSON coverage artifact (`reports/coverage.json`) and refreshed
  `coverage.txt` snapshot documenting module-level thresholds for the
  analytics stack.
- Telemetry bootstrap helper (`server/observability/telemetry.py`) powering the
  new `/api/observability/telemetry` endpoint and runtime metadata annotations.
- Extension contract versioning (`EXTENSION_API_VERSION`), registry contract
  notes, and a builtin webhook notifier showcasing lifecycle webhooks.
- Developer CLI subcommands: `verify` (lint/type/test/security/coverage),
  `check-todos` (priority metadata enforcement), and `scaffold-extension`
  (contract-aware module template generator).
- CI security stage running Bandit and `pip-audit`; Makefile and docs now expose
  matching local commands.
- Future-proofing playbook (`docs/future-proofing.md`) outlining scaling,
  containerisation, migration, and agent safety strategies.
- Incident response, automation, AI interface, and architecture docs updated
  with telemetry guidance, extension contract notes, and new tooling references.
- Diagnostics version loader cache plus `clear_required_versions_cache()` helper
  with coverage to support deterministic diagnostics testing.
- Extension runtime under `server/extensions/` with builtin Prometheus task
  metrics hook and documentation in `EXTENSION_GUIDE.md`.
- Plan observer contract with builtin `plan_metrics` extension and
  `server/observability/metrics.py` helper emitting Prometheus gauges for
  task analytics after each broadcast.
- Lightweight tracing helper (`server/observability/tracing.py`) to annotate
  plan broadcasts without requiring OpenTelemetry at import time.
- Extension documentation updated with plan observer scaffolds and analytics
  export examples; automation docs highlight the new gauges and contract notes.
- `/api/settings` now surfaces extension configuration metadata (modules,
  builtin toggle, registered descriptors) for operators and agents.
- `/api/diagnostics` aggregates runtime metadata, package versions, feature flags, and system state; the admin UI renders a diagnostics panel backed by the same payload.
- Developer CLI `scripts/dev.py` providing `bootstrap`, `coverage-gate`, and
  `bump-version` subcommands used by the Makefile and CI pipeline.
- `server/observability/runtime.py` captures process uptime, deployment
  metadata, and powers enriched health responses.
- Architecture, automation, and incident response documentation (`ARCHITECTURE_OVERVIEW.md`,
  `AUTOMATION.md`, `docs/incident-response.md`).
- Extension loader regression tests exercise explicit module loading,
  missing-registrar warnings, and error handling to backstop the new coverage
  thresholds.
- Stewardship metrics CLI `scripts/audit_metrics.py` exports coverage, complexity, and dependency depth summaries to `reports/system_metrics.json` for automation and reporting.
- `/health/live` and `/health/ready` endpoints expose liveness and readiness probes via the new `HealthStatus` schema.
- `scripts/local_runner.py` provides a reference agent loop that registers, heartbeats, and optionally completes tasks.
- Documentation hub at `docs/index.md`, message schema reference, failure modes guide, and TODO backlog enumerating follow-up work.
- `/api/settings` endpoint exposing rate limit and lease configuration for operators and clients.
- Python CLI now fetches server settings and adjusts heartbeat intervals that would outlive the lease duration.
- CLI runtime summary output with accompanying [docs/cli-runtime.md](docs/cli-runtime.md) walkthrough plus the dependency audit in [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).
- Hardened developer helper scripts: `scripts/run_pytest.py` now shells directly into pytest, while `scripts/run_uvicorn.py` starts uvicorn via the library API and binds to loopback by default for safer local testing.
- Coverage workflow captured in `coverage.txt` to document current package-level coverage baselines.

### Changed
- `/api/settings` includes extension contract version/notes so operators can
  audit plugin compatibility.
- Observability documentation and health guidance highlight
  `/api/observability/telemetry` for instrumentation awareness.
- CI quality matrix now runs a dedicated security stage; `make qa` and
  `scripts/dev.py verify` mirror the updated pipeline.
- Prometheus analytics helper builds gauges from declarative specifications,
  cutting duplicate setup logic and keeping the metrics surface consistent for
  future extensions.
- Builtin Prometheus metrics hook now honours strict type hints and optional
  dependency guards so Ruff and mypy run cleanly on extensions code.
- `TaskOut` uses `ConfigDict(from_attributes=True)` to align with modern
  Pydantic configuration and remove deprecation warnings.
- `TaskService` emits lifecycle events to extension bundles so plugins can react
  to checkouts, completions, and task mutations without altering core logic.
- Extension contract bumped to **2025.2**; telemetry and diagnostics now expose
  plan observer counts plus task analytics gauge metadata.
- `broadcast_plan` gathers analytics once per dispatch, wraps observers in
  tracing spans, and invokes plan observers before WebSocket fan-out.
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

### Removed
- Deprecated `server/interfaces.py` dataclasses in favour of the canonical Pydantic schemas in `server/schema.py`.

### Fixed
- Diagnostics package status parsing reuses the cached requirements metadata,
  avoiding repeated filesystem reads across requests and tests.
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
