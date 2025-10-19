# Changelog

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
