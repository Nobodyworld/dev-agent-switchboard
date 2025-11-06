# Technical Debt Backlog — 2025-11-06

## Priority P1

- **Restore development dependency bootstrap** — `make setup` fails offline when pip cannot download `fastapi==0.120.0`, preventing Bandit, pip-audit, and coverage tooling from running. Mirror the dev requirements or pre-provision wheels so CI and local operators can execute the full security suite without network access. (Refs: `Makefile`, `server/requirements-dev.txt`)

## Priority P2

- **Resolve legacy Ruff violations** — `ruff check .` reports branch-complexity warnings in `client/python/runtime_config.py` and `client/python/switchboard_cli.py` plus unused variables in `server/observability/health.py`. Refactor or add targeted suppressions so linting can be enforced consistently.
- **Re-enable coverage enforcement** — Once dependencies install, run `make coverage` to regenerate `reports/coverage.json` and confirm `scripts/dev.py coverage-gate` passes with the new websocket backoff tests included.

## Priority P3

- **Security tool parity** — After restoring the dev environment, run `bandit -q -r server` and `pip-audit` locally to mirror CI behaviour and capture findings in `SECURITY_NOTES.md` going forward.
- **Optional: Dockerless build path** — Provide a container-free `make build` alternative (e.g., packaging the FastAPI service) for environments without Docker access.
