# Security Notes

## 2026-06-27 — Public-Release Hardening

### Verified

- `pip-audit` initially identified 14 advisories in four pinned packages.
  FastAPI, Starlette, the metrics instrumentator, python-multipart, pytest,
  pytest-asyncio, Black, and Pydantic were upgraded as a compatible set.
- The final Python 3.11 audit reported no known vulnerabilities.
- Bandit passed against production server code; test assertions are excluded.
- Live-file writes now honor configured admin authentication and a streaming
  upload-size limit.
- Atomic task claiming, lease ownership, and expired-heartbeat behavior have
  regression coverage.

### Remaining

- Execute the symlink-escape test on Linux; local Windows policy prevented
  symlink creation.
- Strict mypy remains red and is tracked as a quality gap rather than a
  confirmed vulnerability.

## 2025-11-06 — Websocket Backoff Follow-up Audit

### Findings

- Unable to provision the Python tooling stack offline: `make setup` failed when pip could not reach the package index for `fastapi==0.120.0`. Bandit, pip-audit, and coverage extras were therefore unavailable locally.
- `ruff check .` surfaced existing style issues in legacy client/server modules; none are exploitable but they keep the lint pipeline from running cleanly without targeted ignores.
- No secrets were committed; gitleaks continues to protect the main branch via CI.

### Mitigations & Next Steps

1. Re-run `make setup && make security` in a connected environment to restore Bandit and pip-audit coverage (P1).
2. Capture Ruff clean-up work in `TECH_DEBT.md` so that linting becomes actionable in CI and during local security reviews (P2).
3. Continue to rely on the existing CI `gitleaks` and `pip-audit` stages once dependency installation succeeds; no additional runtime secrets were introduced in this follow-up (P3).

Document owner: gpt-5-codex
