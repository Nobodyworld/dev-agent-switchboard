# Changelog

## Unreleased

### Added
- `/api/settings` endpoint exposing rate limit and lease configuration for operators and clients.
- Python CLI now fetches server settings and adjusts heartbeat intervals that would outlive the lease duration.

### Changed
- Lease duration parsing raises clearer "positive integer" errors and is validated during FastAPI startup, logging the active configuration.
- Settings caching now exposes an aggregated bundle so `/api/settings` and startup logging read a single coherent snapshot while cache reloads keep the views in sync.
- Python CLI surfaces warnings when server settings are missing or invalid and honours per-operation timeouts for `/api/settings` requests.

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
