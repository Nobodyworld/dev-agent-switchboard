# Switchboard Modernization Execution Plan

_Last updated: 2025-02-14_

## Milestone Overview

1. **M1 – Governance & Automation Foundations** (Weeks 1–2)  
   Establish repository policies, standardized tooling, and CI/CD enforcement without touching runtime behavior.
2. **M2 – Type Safety & Code Health** (Weeks 2–3)  
   Enforce strict typing/linting and prune dead code to create a safe baseline for feature work.
3. **M3 – Quality, Testing & Observability** (Weeks 3–4)  
   Build a reliable test pyramid, wire structured logging/metrics/tracing, and guarantee operational visibility.
4. **M4 – Security & Supply Chain** (Weeks 4–5)  
   Harden dependencies, secrets, and configuration management with SBOM, scanning, and policy automation.
5. **M5 – Performance & Resilience** (Weeks 5–6)  
   Improve runtime efficiency, add guardrails (timeouts, retries), and validate scaling characteristics.
6. **M6 – Release & Developer Experience** (Weeks 6–7)  
   Deliver release automation, onboarding docs, and STATUS/CHANGELOG updates for sustainable operations.

Each milestone produces independently reviewable PRs with green CI and documentation updates. STATUS.md must be updated after every merged PR.

---

## Milestone Detail

### M1 – Governance & Automation Foundations

#### Workstream: Repository Governance & Policy
- **Task M1.GOV.1 – Author governance docs & templates** `[tags: docs, DX]`
  - _Goal_: Introduce `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `CODEOWNERS`, LICENSE verification, and PR/issue templates.
  - _Acceptance Criteria_: Docs present at repo root with cross-links from README; `.github/ISSUE_TEMPLATE/*` & `.github/pull_request_template.md` created; CODEOWNERS lists primary reviewers; README references contribution workflow.
  - _Blast Radius_: Documentation only.
  - _Rollback Plan_: Revert commit; no runtime impact.
  - _Status_: 🚧 In progress (governance baseline PR; detect-secrets via pre-commit, gitleaks enforced in CI).
- **Task M1.GOV.2 – Standardize repo metadata** `[tags: DX, docs]`
  - _Goal_: Update README to reference REPORT/PLAN, add badges/placeholders for CI, define labeling scheme in `.github/labels.yml` (if using GitHub CLI automation).
  - _Acceptance Criteria_: README includes governance links; label schema documented; make sure no runtime changes.
  - _Blast Radius_: Documentation + GitHub metadata.
  - _Rollback Plan_: Revert commit.
  - _Status_: 🚧 In progress (governance baseline PR; detect-secrets via pre-commit, gitleaks enforced in CI).

#### Workstream: Tooling & Formatting Baseline
- **Task M1.TOOL.1 – Adopt EditorConfig & consistent formatters** `[tags: DX]`
  - _Goal_: Add `.editorconfig`, configure Black/Ruff/Prettier (for web) defaults, update Makefile/pyproject to enforce.
  - _Acceptance Criteria_: Config files committed; formatters run cleanly; documented in CONTRIBUTING.
  - _Blast Radius_: Formatting configuration only (no code touched yet).
  - _Rollback Plan_: Remove config files.
  - _Status_: 🚧 In progress (governance baseline PR).
- **Task M1.TOOL.2 – Expand pre-commit hooks** `[tags: DX, testing]`
  - _Goal_: Add hooks for Black, Ruff (lint+format), Prettier, commitlint, gitleaks (run-as-check), mypy stub check; ensure `pre-commit install` instructions documented.
  - _Acceptance Criteria_: `.pre-commit-config.yaml` updated; `pre-commit run --all-files` passes locally.
  - _Blast Radius_: Tooling config; initial run may reformat later tasks.
  - _Rollback Plan_: Revert config adjustments.
  - _Status_: 🚧 In progress (governance baseline PR).

#### Workstream: CI/CD Bootstrap
- **Task M1.CI.1 – Rebuild GitHub Actions pipeline** `[tags: DX, testing, reliability]`
  - _Goal_: Replace/augment existing workflow with matrix jobs (lint, type, test, build docs) + caching + artifact upload + status badge.
  - _Acceptance Criteria_: `.github/workflows/ci.yml` runs lint (ruff/black check), type (mypy), tests (pytest), docs (link check) on push/pr; uses pip cache; required checks documented.
  - _Blast Radius_: CI only.
  - _Rollback Plan_: Revert workflow file.
  - _Status_: 🚧 In progress (governance baseline PR).
- **Task M1.CI.2 – Add Renovate + commitlint enforcement** `[tags: security, DX]`
  - _Goal_: Introduce `renovate.json` for dependency updates, commitlint config & GitHub Action gating PR titles (Conventional Commits).
  - _Acceptance Criteria_: Renovate config valid (validated via Renovate JSON schema), commitlint action passes; README/CONTRIBUTING mention commit format.
  - _Blast Radius_: CI + doc updates.
  - _Rollback Plan_: Revert config.
  - _Status_: 🚧 In progress (governance baseline PR).

### M2 – Type Safety & Code Health

#### Workstream: Typing Enforcement
- **Task M2.TYPE.1 – Enable mypy strict mode** `[tags: testing, reliability, DX]`
  - _Goal_: Update `mypy.ini` for `strict = True`, add missing type hints/stubs, address `type: ignore` usage.
  - _Acceptance Criteria_: `mypy` passes with strict settings; all ignores justified with comments.
  - _Blast Radius_: Python modules touched for annotations.
  - _Rollback Plan_: Revert to previous config; ensure tests still pass.
- **Task M2.TYPE.2 – Tighten Ruff configuration** `[tags: DX, reliability]`
  - _Goal_: Expand Ruff rule set (imports, complexity, docstrings), add per-module `__all__` where necessary.
  - _Acceptance Criteria_: Ruff passes; no suppressed warnings without explanation.
  - _Blast Radius_: Python modules/ruff config.
  - _Rollback Plan_: Revert config and targeted fixes.

#### Workstream: Code Health & Dead Code
- **Task M2.HEALTH.1 – Remove unused modules & consolidate shims** `[tags: DX]`
  - _Goal_: Identify dead code (REPORTS, duplicate shims) and either remove or mark deprecated behind feature flag while preserving API compatibility.
  - _Acceptance Criteria_: Documented removals in CHANGELOG; tests adjusted; backward compatibility wrappers remain if required with warnings.
  - _Blast Radius_: Modules removed; ensure packaging unaffected.
  - _Rollback Plan_: Restore removed files from history.
- **Task M2.HEALTH.2 – Modularize server/app.py** `[tags: performance, reliability]`
  - _Goal_: Extract routers, broadcasters, and startup logic into dedicated modules; maintain FastAPI behavior.
  - _Acceptance Criteria_: App factory introduced (`create_app()`), tests updated, coverage for extracted modules.
  - _Blast Radius_: Server initialization; thorough regression tests required.
  - _Rollback Plan_: Revert commit; redeploy previous version.

### M3 – Quality, Testing & Observability

#### Workstream: Test Pyramid
- **Task M3.TEST.1 – Establish unit/integration/e2e suites** `[tags: testing, reliability]`
  - _Goal_: Create clear directories for unit/integration/e2e; add fixtures for DB and WebSocket tests; ensure deterministic seeds.
  - _Acceptance Criteria_: `pytest -m unit`, `-m integration`, `-m e2e` each runnable; coverage report generated.
  - _Blast Radius_: Test suite + supporting code (feature flags only).
  - _Rollback Plan_: Revert tests + config.
- **Task M3.TEST.2 – Add CLI golden/snapshot tests** `[tags: testing, DX]`
  - _Goal_: Snapshot CLI outputs for key flows (checkout, heartbeat, completion) using recorded fixtures.
  - _Acceptance Criteria_: Snapshots stored under `tests/snapshots`; tests pass deterministically.
  - _Blast Radius_: Tests only.
  - _Rollback Plan_: Remove snapshots/tests.

#### Workstream: Observability
- **Task M3.OBS.1 – Standardize structured logging & metrics** `[tags: observability, reliability]`
  - _Goal_: Ensure request/lease IDs propagate; unify logging format; verify Prometheus/OTel exporters configured with health endpoints.
  - _Acceptance Criteria_: Logging middleware adds correlation IDs; `/metrics` available; instrumentation docs updated.
  - _Blast Radius_: Server runtime + docs.
  - _Rollback Plan_: Revert instrumentation changes.
- **Task M3.OBS.2 – Add health/readiness probes & dashboards** `[tags: observability, reliability]`
  - _Goal_: Implement `/healthz` & `/readyz` endpoints, create dashboards-as-code (Grafana JSON) stored in repo.
  - _Acceptance Criteria_: Endpoints respond per spec; dashboards versioned; docs reference setup.
  - _Blast Radius_: Server endpoints; minimal.
  - _Rollback Plan_: Remove endpoints + dashboards.

### M4 – Security & Supply Chain

#### Workstream: Dependency Hygiene
- **Task M4.SEC.1 – Lock dependencies & generate SBOM** `[tags: security]`
  - _Goal_: Adopt `uv pip compile` or `pip-tools` to manage lockfiles; generate SBOM via Syft/CycloneDX as artifact.
  - _Acceptance Criteria_: Lockfiles present; CI job uploads SBOM; docs explain regeneration.
  - _Blast Radius_: Dependency management; ensure compatibility.
  - _Rollback Plan_: Revert lockfile/tooling commits.
- **Task M4.SEC.2 – Automate dependency auditing** `[tags: security, CI]`
  - _Goal_: Add pip-audit/Safety scans in CI; integrate with Renovate policies.
  - _Acceptance Criteria_: CI fails on high severity vulnerabilities; suppressed CVEs documented.
  - _Blast Radius_: CI only.
  - _Rollback Plan_: Disable workflow step.

#### Workstream: Secrets & Configuration
- **Task M4.SEC.3 – Implement secret scanning & policies** `[tags: security]`
  - _Goal_: Add gitleaks config, GitHub secret scanning alerts, `.gitignore` hardening, `.env.example` and config validation (Pydantic `BaseSettings`).
  - _Acceptance Criteria_: `gitleaks detect` clean; `.env.example` matches settings; runtime validates config at startup.
  - _Blast Radius_: Server configuration; small risk if validation rejects existing env vars (documented).
  - _Rollback Plan_: Revert config validation or gate behind feature flag.
- **Task M4.SEC.4 – Harden file upload & auth surfaces** `[tags: security, reliability]`
  - _Goal_: Add size/content-type limits, checksums, and optional authentication hooks.
  - _Acceptance Criteria_: Upload endpoints enforce limits; tests cover malicious payload scenarios; docs updated.
  - _Blast Radius_: API endpoints; must regression-test clients.
  - _Rollback Plan_: Toggle limits via config or revert commit.

### M5 – Performance & Resilience

#### Workstream: Runtime Resilience
- **Task M5.RES.1 – Add timeout/retry/circuit breaker patterns** `[tags: reliability, performance]`
  - _Goal_: Introduce HTTP client timeouts, database retry logic with exponential backoff, circuit breaker for WebSocket broadcasts.
  - _Acceptance Criteria_: Configurable defaults; tests simulate timeouts; metrics emitted for retries.
  - _Blast Radius_: Client + server runtime; ensure backwards compatibility.
  - _Rollback Plan_: Disable via feature flags, revert if necessary.

#### Workstream: Database & Storage
- **Task M5.RES.2 – Optimize database schema** `[tags: performance]`
  - _Goal_: Add indices on `leases`/`tasks` lookup columns, ensure Alembic migrations cover runtime DDL, add migration tests.
  - _Acceptance Criteria_: Alembic revisions created; tests run migrations forward/back; runtime startup no longer executes raw SQL.
  - _Blast Radius_: Database; coordinate release with migration deployment.
  - _Rollback Plan_: Revert migration (downgrade) and code changes.

#### Workstream: Profiling & Benchmarking
- **Task M5.RES.3 – Introduce performance benchmarks** `[tags: performance, testing]`
  - _Goal_: Add `pytest-benchmark` or `asv` benchmarks for checkout/heartbeat flows; integrate optional CI job.
  - _Acceptance Criteria_: Benchmarks run locally; baseline results stored; docs explain usage.
  - _Blast Radius_: Tests only.
  - _Rollback Plan_: Remove benchmark suite.

### M6 – Release & Developer Experience

#### Workstream: Release Automation
- **Task M6.REL.1 – Implement semantic release workflow** `[tags: DX, reliability]`
  - _Goal_: Configure Semantic Release (or Release Please) to publish versions, changelog, GitHub releases, and Python package builds.
  - _Acceptance Criteria_: `.github/workflows/release.yml` publishes tags on main merges; CHANGELOG auto-updated.
  - _Blast Radius_: CI/release pipeline; ensure dry-run before enabling.
  - _Rollback Plan_: Disable workflow, revert config.

#### Workstream: Developer Onboarding & Docs
- **Task M6.DX.1 – Create First Hour Guide & troubleshooting** `[tags: docs, DX]`
  - _Goal_: Document setup via `README`, `docs/first-hour.md`, `docs/troubleshooting.md`; align with Makefile commands.
  - _Acceptance Criteria_: Guides exist; validated by running bootstrap script in clean environment.
  - _Blast Radius_: Docs only.
  - _Rollback Plan_: Revert docs.
- **Task M6.DX.2 – Add one-command bootstrap & env parity** `[tags: DX, reliability]`
  - _Goal_: Provide `make dev`/`just dev` to launch app + watcher + telemetry; include seed data + fixture resets.
  - _Acceptance Criteria_: Command spins up services via docker-compose; docs updated; developers can run within 5 minutes.
  - _Blast Radius_: Makefile/scripts; ensure idempotent.
  - _Rollback Plan_: Revert Makefile/scripts.

#### Workstream: Status & Hand-off
- **Task M6.DOC.1 – Final STATUS.md & audit trail** `[tags: docs]`
  - _Goal_: Summarize completed work, remaining risks, and recommended roadmap; ensure STATUS.md references REPORT/PLAN updates.
  - _Acceptance Criteria_: STATUS.md updated post-final PR; cross-links validated.
  - _Blast Radius_: Docs only.
  - _Rollback Plan_: Revert update.

---

## Sequencing & Dependencies

- M1 tasks unblock stricter lint/type checks; must complete before M2.
- M2 modularization (`M2.HEALTH.2`) should land before observability/security work to avoid rework; coordinate with testing improvements (M3.TEST.1).
- Security tasks (M4) depend on standardized CI from M1 and modular server from M2.
- Performance optimizations (M5) require reliable tests/observability (M3) and secure configuration (M4).
- Release automation (M6.REL.1) depends on successful CI/CD and semantic versioning decisions captured in earlier milestones.

## Blockers & Assumptions

- Assumes GitHub Actions remains primary CI/CD provider.
- External dependencies (Playwright, browsers) may be unavailable in some environments; plan to allow skips with documentation.
- Production database assumed to be SQLite or Postgres; migrations must target supported engines (confirm before M5.RES.2).
- Adoption of commitlint/Conventional Commits requires team buy-in; document migration path in CONTRIBUTING.

## Rollback Strategy

- Each task produces isolated commits/PRs; revert via `git revert` if issues surface.
- Maintain feature flags (environment variables) for runtime-affecting changes (security, resilience) to allow staged rollouts.
- CI pipelines will include dry-run modes for release/security workflows before enforcing on main.

## Acceptance Checklist (for plan completion)

- [ ] REPORT.md aligned with latest architecture state.
- [ ] PLAN.md (this document) kept up to date as tasks complete.
- [ ] STATUS.md appended after each PR with summary + next steps.
- [ ] All milestones tracked with GitHub Projects or Issues referencing task IDs.
