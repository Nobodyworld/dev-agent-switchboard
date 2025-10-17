# Switchboard Audit Report

## Structure & Dependency Map
- **server/** – FastAPI application (`app.py`) backed by SQLAlchemy async engine (`db.py`), domain logic (`task_logic.py`), models, and auxiliary subsystems (file store, instrumentation, rate limiting, ExecPlan registry).
- **client/python/** – Requests-based SDK (`switchboard_client.py`) and CLI (`switchboard_cli.py`) packaged via `pyproject.toml` with examples/tests.
- **web/** – Static HTMX-powered admin dashboard served by the API along with shared assets.
- **tests/** – Combined server/client regression suite plus root-level shim checks; `scripts/run_pytest.py` orchestrates end-to-end validation.

## Key Findings
- `server/app.py` centralizes routing, serialization, and WebSocket broadcasting; tight coupling makes targeted changes harder and complicates dependency injection for tests.
- Rate limit middleware relies on cached global settings, so prior overrides can leak into later scenarios unless `reload_rate_limit_settings()` is called; integration environments must reset state explicitly to avoid false positives.
- Live file uploads accept arbitrary payload sizes; without quota checks or content filtering the API is susceptible to resource exhaustion by malicious clients.
- WebSocket broadcasting previously lacked direct unit coverage for failure scenarios, leaving stale-connection cleanup unverified and increasing risk of leaked state.

## Risk Notes
- Cached rate-limit configuration combined with global middleware state can produce spurious 429 responses after tests mutate environment variables; production deployments should surface health metrics to detect similar drift.
- File storage writes are immediate and synchronous; large uploads or slow disks block request handling because there is no streaming/async buffering.
- Monolithic `app.py` makes it easy to introduce regressions when modifying plan broadcast logic because business rules and transport concerns are interwoven.

## Test Posture
- Comprehensive pytest suite spans REST endpoints, file store, ExecPlan registry, rate limiting, and WebSocket flows. Coverage is strong but previously lacked explicit assertions for stale WebSocket pruning; new tests address this gap.
- Integration test `test_websocket_plan` exercises a live uvicorn server; adjustments ensure compatibility with uvicorn ≥0.30 and guard against shared rate-limit state between tests.

## CI/CD Posture
- GitHub Actions `CI` workflow mirrors local entry points: installs `server/requirements-dev.txt`, runs `python scripts/run_pytest.py`, and optionally formats/lints/types based on repo variables. Makefile helpers (`make run`, `make test`, `make qa`) provide parity for contributors.

## Update Modes Selected
- **Test & Verify** – Expanded coverage around WebSocket broadcasting, hardened integration fixtures against dependency changes, and ensured rate-limit state resets so regressions surface deterministically.

## Verification
- `python scripts/run_pytest.py` — passes after installing required dependencies (45 passed, 2 skipped). See `scripts/run_pytest.py` output captured in this run.
