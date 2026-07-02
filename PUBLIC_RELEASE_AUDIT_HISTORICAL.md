# Public Release Audit

## Release-Readiness Addendum — 2026-06-30

- Clean environment: `C:\Users\Nobod\Documents\GitHub\dev-agent-switchboard-release`.
- Baseline SHA: `fc9ccae35366094b34c035a7e19ece4d87e7703b`.
- Original dirty workspace: preserved; not used as the validation source.
- Hosted CI: workflows are active, but repository Actions are disabled by owner policy (`actions/permissions.enabled=false`). Clean-clone validation is authoritative until Actions is re-enabled.
- License: replaced proprietary/confidential notice with Apache License 2.0 and `Copyright 2026 Travis William Jones`; Python client metadata declares `Apache-2.0`.

Clean-clone gate results recorded during this remediation pass:

- `pre-commit run --all-files --show-diff-on-failure`: passed after formatting, lint, and synthetic secret-fixture remediation.
- `ruff check server client scripts tests web switchboard_cli.py switchboard_client.py`: passed.
- `black --check server client scripts tests web switchboard_cli.py switchboard_client.py`: passed.
- `mypy --config-file mypy.ini server client scripts`: passed for the configured supported type-check surface; optional instrumentation and observability adapters are explicitly scoped in `mypy.ini`.
- `pytest -q`: 229 passed, 1 skipped.
- `SWITCHBOARD_STRICT_PLAYWRIGHT=1 pytest web/tests/test_ui.py -rA`: 2 passed, 0 skipped.
- Coverage gate: passed after collecting and enforcing thresholds for `server/extensions`, `server.observability`, `server.application.configuration_service`, and `server.application.task_service`.
- `bandit -q -r server -x server/tests`: passed.
- `pip-audit --progress-spinner=off -r server/requirements-dev.txt`: no known vulnerabilities.
- Gitleaks full-history scan: passed.
- Lychee documentation-link validation for `README.md` and `docs/**/*.md`: passed.

Residual warnings:

- Full pytest emits Starlette/httpx and websockets deprecation warnings from dependencies.
- Hosted CI cannot report until GitHub Actions is re-enabled for this repository.

- Repository: dev-agent-switchboard
- Audit date: 2026-06-22
- Branch audited: main
- Auditor mode: direct-to-main, no PR

## Scope

This Phase 1 audit assesses employer/public-release readiness and identifies blockers without bundling broad implementation changes.

## Safety Preconditions (Verified)

- main branch confirmed.
- Working tree clean before edits.
- git pull --ff-only origin main succeeded.
- Annotated rollback tag created and pushed:
  - public-release-baseline-2026-06-22

## Repository Snapshot

- Stack: FastAPI service + Python client + web dashboard.
- Core surfaces:
  - server/api and server/application
  - server/file_store and live file mirror endpoints
  - client/python and local runner scripts
  - docs architecture/guides/reports hubs
- Key metadata present:
  - pyproject.toml
  - .github/workflows/ci.yml
  - .github/workflows/commitlint.yml
  - Makefile
  - LICENSE

## Findings By Area

### 1) Current files and structure

- Repository has clear separation of API/domain/infrastructure/client/docs.
- Documentation volume is high; must ensure public claims only reflect validated behavior.

Status: Partial

### 2) Full Git history (high-level)

- mainline is active and recently updated with CI badge/docs cleanup and prior stabilization work.

Status: Partial

### 3) Secrets and credentials

- History filename scan found expected examples/baselines (`ops/.env.example`, `.secrets.baseline`).
- No direct private-key artifact filenames were identified in quick scan.

Status: Partial

### 4) Personal/private information

- No explicit personal PII artifacts found in initial review.

Status: Partial

### 5) Generated files and hygiene

- Quick tracked-file pattern check did not show common generated roots checked in.

Status: Partial

### 6) Dependency vulnerabilities

- Python 3.11 audit initially found 14 advisories across Black, pytest,
  python-multipart, and Starlette.
- Runtime and development pins were upgraded, including the compatible
  FastAPI/Starlette and instrumentation set.
- Final `pip-audit --progress-spinner=off`: no known vulnerabilities.
- `bandit -q -r server -x server/tests`: passed.

Status: Verified locally (2026-06-27)

### 7) Licensing

- LICENSE exists.
- No license replacement performed.

Status: Verified (presence only)

### 8) Broken documentation links

- Link-check output not captured yet.

Status: Not Yet Verified

### 9) Build and runtime instructions

- README quickstart targets Python 3.11+.
- Isolated Python 3.11.14 validation completed on Windows with pinned
  dependencies. The Makefile remains POSIX-oriented; Windows validation used
  direct virtual-environment commands.

Status: Verified for direct Windows commands; Makefile portability remains partial

### 10) CI/build truth and quality gates

- CI workflow exists and runs on push/pull_request with build + test flow.
- Local Python 3.11 results:
  - pytest: 226 passed, 2 skipped.
  - Ruff: passed.
  - Bandit: passed after excluding test assertions from the production scan.
  - TODO metadata check: passed after excluding virtual environments.
  - Coverage thresholds: passed.
  - pip-audit: no known vulnerabilities.
  - strict mypy: failed with 76 errors in 27 files.

Status: Partial (strict typing remains a release-quality gap)

### 11) Public-release blockers (initial)

Potential blockers for next phases:

- Resolved: atomic checkout, lease ownership/expiry, and dependency unlocking now
  have objective regression coverage.
- Resolved: configured admin authentication protects live-file writes and a
  configurable streaming upload limit rejects oversized bodies.
- Pending Linux verification: symlink-escape regression (Windows account could
  not create symlinks).
- P1 candidate: simplify employer-facing narrative while preserving operational truth.
- P1 blocker: resolve or deliberately scope the strict-mypy backlog.

## Next-Phase Remediation Plan

1. Phase 2 (CI/build integrity)

- Run and harden local quality gates under owner policy where Actions may be disabled.
- Verify tests are fatal and security scans are not advisory-only in release path.

1. Phase 3 (critical fixes)

- Address switchboard-specific P0 controls (leases, concurrency, auth, live-file security).

1. Phase 4 (employer-facing docs)

- Update README/docs to only claim verified behavior.

1. Phase 5 (clean-clone validation)

- Execute full documented process from clean clone and record objective outcomes.

## Commands Executed During Audit

- git rev-parse --abbrev-ref HEAD
- git status --porcelain
- git pull --ff-only origin main
- git tag -a public-release-baseline-2026-06-22 -m "Baseline before employer portfolio cleanup"
- git push origin public-release-baseline-2026-06-22
- git log --oneline --decorate -n 20
- git remote -v
- workflow/docs and hygiene inspections

## Local-validation policy note

GitHub Actions may be disabled by owner policy for portions of the portfolio. Local and clean-clone validation will be treated as authoritative where remote CI is unavailable.
