# Changelog

## Unreleased

### Added
- `server/interfaces.py` and `server/application/task_service.py` define immutable queue, task, and agent interfaces powering the checkout workflow.
- `/health/live` and `/health/ready` endpoints expose liveness and readiness probes via the new `HealthStatus` schema.
- `scripts/local_runner.py` provides a reference agent loop that registers, heartbeats, and optionally completes tasks.
- Documentation hub at `docs/index.md`, message schema reference, failure modes guide, and TODO backlog enumerating follow-up work.
- `/api/settings` endpoint exposing rate limit and lease configuration for operators and clients.
- Python CLI now fetches server settings and adjusts heartbeat intervals that would outlive the lease duration.

### Changed
- README now introduces Switchboard via What/Why/How framing, highlights the local runner, and documents new health probes.
- Module docstrings across `server/` and the Python client follow NumPy style for consistent parameter/return documentation.
- Existing `docs/architecture.md` expanded with application/service context, while `docs/INDEX.md` links to the new documentation hub.
- License replaced with the Switchboard Proprietary notice reflecting the project's closed-source status.
- Lease duration parsing raises clearer "positive integer" errors and is validated during FastAPI startup, logging the active configuration.
- Settings caching now exposes an aggregated bundle so `/api/settings` and startup logging read a single coherent snapshot while cache reloads keep the views in sync.
- Python CLI surfaces warnings when server settings are missing or invalid and honours per-operation timeouts for `/api/settings` requests.
- Task repository adapters batch dependency lookups and power new `TaskService`-focused tests that cover checkout, completion, and abandon flows without API indirection.

### Fixed
- Restored missing imports in `server/tests/conftest.py` so database reset fixtures execute reliably during test runs.

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
