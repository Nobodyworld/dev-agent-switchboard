# Security Notes

These notes preserve dated security-review findings. They are historical records, not a substitute for the current security policy, active release audit, or protected GitHub Actions results.

For current guidance and status, use:

- [`SECURITY.md`](SECURITY.md) for supported reporting and deployment boundaries;
- [`PUBLIC_RELEASE_AUDIT.md`](PUBLIC_RELEASE_AUDIT.md) for the current developer-preview and formal-release disposition;
- [`docs/operations/local-worker.md`](docs/operations/local-worker.md) for trusted repository mapping, worker configuration, retained evidence, and local execution limitations;
- issue [#95](https://github.com/Nobodyworld/dev-agent-switchboard/issues/95) for release gates;
- issue [#104](https://github.com/Nobodyworld/dev-agent-switchboard/issues/104) for Linux, Docker, and clean-environment validation;
- the active pull request and living ExecPlan for exact run identifiers, test counts, coverage measurements, and environment limitations.

## 2026-06-27 — Public-Release Hardening Snapshot

### Verified at that time

- `pip-audit` initially identified 14 advisories in four pinned packages.
  FastAPI, Starlette, the metrics instrumentator, python-multipart, pytest,
  pytest-asyncio, Black, and Pydantic were upgraded as a compatible set.
- The final Python 3.11 audit reported no known vulnerabilities.
- Bandit passed against production server code; test assertions were excluded.
- Live-file writes honored configured admin authentication and a streaming
  upload-size limit.
- Atomic task claiming, lease ownership, and expired-heartbeat behavior had
  regression coverage.

### Then-open items

- The Linux symlink-escape regression still required execution on a Linux-capable environment. That formal-release gate remains tracked in #104.
- Strict Mypy was red in this June 2026 snapshot. That statement is historical: the current protected CI matrix includes a passing strict Mypy job. Consult the active workflow and release records rather than treating this dated result as current.

## 2025-11-06 — WebSocket Backoff Follow-up Snapshot

### Findings at that time

- The Python tooling stack could not be provisioned offline because `make setup`
  could not reach the package index for `fastapi==0.120.0`. Bandit, pip-audit,
  and coverage extras were therefore unavailable in that environment.
- `ruff check .` surfaced style issues in legacy client/server modules. These were
  quality findings, not evidence of an exploitable vulnerability.
- No committed secrets were identified in that review; the repository now uses
  protected full-history Gitleaks validation in CI.

### Historical follow-up recommendations

1. Re-run security tooling in a connected environment.
2. Track lint cleanup as technical debt rather than weakening the gate.
3. Continue using CI-backed Gitleaks and dependency-audit evidence.

These recommendations are retained for history. Current status belongs in the active audit, issues, pull requests, and workflow results linked above.
