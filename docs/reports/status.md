# Public-Release Hardening Status

_Last updated: 2026-06-27_

## Verified locally

- Atomic task claiming permits exactly one winner during a two-agent checkout race.
- Lease ownership checks reject wrong-agent lifecycle actions and expired heartbeats.
- Live-file paths reject traversal; configured admin authentication protects writes.
- Live-file uploads enforce `SWITCHBOARD_MAX_LIVE_FILE_BYTES`.
- The complete Python 3.11 suite passes: 226 passed and 2 skipped.
- Ruff, Bandit, TODO policy, coverage thresholds, and pip-audit pass.

## Remaining

- Execute the symlink-escape regression on Linux; Windows symlink creation was unavailable.
- Run and record the documentation link checker.
- Resolve the existing strict-mypy backlog before describing the full quality gate as green.

The authoritative work queue is [TASKLIST.md](../TASKLIST.md), and release-readiness
evidence is recorded in [PUBLIC_RELEASE_AUDIT.md](../../PUBLIC_RELEASE_AUDIT.md).
