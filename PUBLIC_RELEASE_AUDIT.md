# Public Release Audit

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

- Security tooling in Makefile includes bandit.
- Full vulnerability/audit output is not yet recorded in this phase.

Status: Not Yet Verified

### 7) Licensing

- LICENSE exists.
- No license replacement performed.

Status: Verified (presence only)

### 8) Broken documentation links

- Link-check output not captured yet.

Status: Not Yet Verified

### 9) Build and runtime instructions

- README quickstart targets Python 3.11+.
- Makefile defaults to POSIX shell venv activation path (`$(VENV)/bin/...`), which may be frictional on Windows unless adapted.

Status: Partial

### 10) CI/build truth and quality gates

- CI workflow exists and runs on push/pull_request with build + test flow.
- Local gate in Makefile includes lint/typecheck/test/security/coverage/todo checks.

Status: Partial

### 11) Public-release blockers (initial)

Potential blockers for next phases:

- P0 candidate: validate lease ownership, concurrency guarantees, and dependency unlocking behavior with objective tests and documented outcomes.
- P0 candidate: verify privileged endpoint and live-file handling security assumptions (admin token paths, write scopes, path safety).
- P1 candidate: simplify employer-facing narrative while preserving operational truth.
- P1 candidate: ensure documented coverage scope and observability claims are reproducible in local validation mode.

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
