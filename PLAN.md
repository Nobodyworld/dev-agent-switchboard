# Switchboard Modernization Execution Plan

_Last updated: 2025-02-15_

## Milestones Overview
1. **M1 – Governance & Automation Baseline (Week 1)**
   - Deliver repo policies, formatting, linting, CI guardrails without touching runtime behavior.
   - _Exit criteria_: All governance artifacts refreshed, CI rebuild approved, pre-commit enforced.
2. **M2 – Typed Code Health (Weeks 2–3)**
   - Enforce strict typing/linting, prune dead code, modularize hotspots.
   - _Exit criteria_: `mypy --strict` clean, Ruff extended ruleset green, high-risk dead code removed with CHANGELOG entries.
3. **M3 – Quality, Testing & Observability (Weeks 3–4)**
   - Establish test pyramid, structured logging, metrics, health probes.
   - _Exit criteria_: ≥80% coverage on critical modules, structured logging middleware deployed behind feature flag, health checks validated.
4. **M4 – Security & Supply Chain (Weeks 4–5)**
   - Harden dependencies, configuration, and file uploads; automate scanning + SBOM.
   - _Exit criteria_: Lockfiles committed, SBOM artifacts built in CI, config validation enforced.
5. **M5 – Performance & Resilience (Weeks 5–6)**
   - Add timeouts, retries, DB optimizations, benchmarks.
   - _Exit criteria_: Benchmarks produce baseline, resilience tests cover retries/timeouts, migrations run without runtime DDL.
6. **M6 – Releases & Developer Experience (Weeks 6–7)**
   - Automate releases, bootstrap scripts, final documentation and STATUS hand-off.
   - _Exit criteria_: Semantic release dry-run executed, onboarding guide validated by fresh-clone test, STATUS.md finalized.

Each milestone is composed of parallelizable workstreams; tasks specify tags, prerequisites, and rollback strategies. Update `STATUS.md` after every merged PR.

---

### Delivery Governance
- **Change Management** — Use Conventional Commits; ship tightly scoped PRs with aligned docs/tests.
- **Risk Mitigation** — Prefer feature flags for runtime-affecting work until confidence is proven via canary/staging validation.
- **Acceptance Evidence** — Attach screenshots, metrics, or logs for UI/observability changes and link CI artifacts in PRs.
- **Cross-Doc Sync** — Mirror plan/report updates to README/STATUS summaries to avoid documentation drift.

---

## Milestone Detail

### M1 – Governance & Automation Baseline

_Objective_: Guarantee every contribution receives deterministic automated feedback before merge.

#### Workstream: Repository Governance & Policy
- **Task M1.GOV.1 – Refresh governance docs & templates** `[tags: docs, DX]`
  - _Goal_: Normalize LICENSE, CODEOWNERS, CODE_OF_CONDUCT, CONTRIBUTING, SECURITY, SUPPORT, PR/issue templates, README cross-links.
  - _Acceptance Criteria_: All governance docs present and referenced; `.github/ISSUE_TEMPLATE/*` + PR template align with CONTRIBUTING; README links governance bundle.
  - _Blast Radius_: Documentation only.
  - _Rollback Plan_: Revert documentation commit.
  - _Prerequisites_: None.
  - _Blockers_: Await sign-off on CODEOWNERS list (identify maintainers).
  - _Status_: Planned.
- **Task M1.GOV.2 – Label schema & project metadata** `[tags: DX, docs]`
  - _Goal_: Define label taxonomy in `.github/labels.yml`, update README/STATUS to describe workflow signals.
  - _Acceptance Criteria_: Labels documented; automation script or instructions provided; README references label usage.
  - _Blast Radius_: Docs/GitHub metadata.
  - _Rollback Plan_: Revert metadata changes.
  - _Prerequisites_: M1.GOV.1 (governance docs).
  - _Blockers_: GitHub permissions for label sync.
  - _Status_: Planned.

#### Workstream: Tooling & Formatting Baseline
- **Task M1.TOOL.1 – Adopt EditorConfig & formatter stack** `[tags: DX]`
  - _Goal_: Introduce `.editorconfig`, lock in Black/Ruff for Python, Prettier for web assets, update Makefile instructions.
  - _Acceptance Criteria_: Config files committed; `make fmt`/`pre-commit run --all-files` succeed without code changes (format-only PRs follow later).
  - _Blast Radius_: Config only.
  - _Rollback Plan_: Revert configs.
  - _Prerequisites_: None.
  - _Blockers_: Ensure Prettier dependencies vendorized or invoked via `npx` without global install.
  - _Status_: Planned.
- **Task M1.TOOL.2 – Expand pre-commit hooks & commit policy** `[tags: DX, testing]`
  - _Goal_: Configure `.pre-commit-config.yaml` for Ruff, Black, Prettier, detect-secrets/gitleaks, mypy stub check; enforce Conventional Commits via commitlint hook.
  - _Acceptance Criteria_: `pre-commit run --all-files` clean; commit-msg hook installed; documented in CONTRIBUTING.
  - _Blast Radius_: Tooling config.
  - _Rollback Plan_: Revert hook config.
  - _Prerequisites_: M1.TOOL.1 (shared formatter config).
  - _Blockers_: None.
  - _Status_: Planned.

#### Workstream: CI/CD Bootstrap
- **Task M1.CI.1 – Rebuild CI pipeline with caching** `[tags: DX, testing, reliability]`
  - _Goal_: Replace `.github/workflows/ci.yml` with matrix (py311/py312), caching via `actions/setup-python`, run lint/type/test/docs/security.
  - _Acceptance Criteria_: CI produces cached runs, uploads coverage + junit artifacts, enforces status checks.
  - _Blast Radius_: CI only.
  - _Rollback Plan_: Restore previous workflow.
  - _Prerequisites_: M1.TOOL.1/M1.TOOL.2 (consistent tooling).
  - _Blockers_: None.
  - _Status_: Planned.
- **Task M1.CI.1a – Instrument CI & wire notifications** `[tags: reliability, observability, DX]`
  - _Goal_: Publish job duration metrics, capture cache hit ratios, and send failure notifications to maintainers (Slack/email) with documented runbook.
  - _Acceptance Criteria_: Workflow emits metrics artifact (JSON/Prometheus), notifications validated via test hook, runbook linked from CONTRIBUTING.
  - _Blast Radius_: CI + documentation.
  - _Rollback Plan_: Disable instrumentation/notification steps via workflow revert.
  - _Prerequisites_: M1.CI.1.
  - _Blockers_: Access to notification channel; ensure secrets managed via OIDC or repo-level configuration.
  - _Status_: Planned.
- **Task M1.CI.2 – Renovate & commitlint enforcement** `[tags: security, DX]`
  - _Goal_: Validate `renovate.json`, add Renovate onboarding docs, ensure `commitlint.yml` gating PR titles.
  - _Acceptance Criteria_: Renovate config passes JSON schema; README/CONTRIBUTING mention update workflow; commitlint action required in branch protection.
  - _Blast Radius_: CI/config.
  - _Rollback Plan_: Revert config.
  - _Prerequisites_: M1.GOV.1 (docs) + M1.TOOL.2 (commit policy).
  - _Blockers_: Enable Renovate app on repo.
  - _Status_: Planned.

### M2 – Typed Code Health

_Objective_: Make type errors impossible to merge and codify module boundaries for safe refactors.

#### Workstream: Typing Enforcement
- **Task M2.TYPE.1 – Enable mypy strict mode** `[tags: testing, reliability, DX]`
  - _Goal_: Update `mypy.ini` to strict, annotate hot modules (models, task_logic, settings, clients), minimize `type: ignore`.
  - _Acceptance Criteria_: `mypy --strict` passes in CI; ignores justified inline.
  - _Blast Radius_: Python modules touched for annotations only.
  - _Rollback Plan_: Revert annotations/config.
  - _Prerequisites_: M1.TOOL.2 (pre-commit/mypy hook).
  - _Blockers_: Third-party stubs availability (Requests/FastAPI) — document shim packages if missing.
  - _Status_: Planned.
- **Task M2.TYPE.2 – Tighten Ruff lint & enforce docstrings** `[tags: DX, reliability]`
  - _Goal_: Expand Ruff ruleset (complexity, docstrings, import hygiene), fix violations, introduce module `__all__` where needed.
  - _Acceptance Criteria_: `ruff check` passes; exceptions documented.
  - _Blast Radius_: Python modules.
  - _Rollback Plan_: Revert changes.
  - _Prerequisites_: M1.TOOL.2, runs after M2.TYPE.1 to avoid conflict.
  - _Blockers_: None.
  - _Status_: Planned.

#### Workstream: Code Health & Modularization
- **Task M2.HEALTH.1 – Remove dead code & consolidate shims** `[tags: DX]`
  - _Goal_: Audit `REPORTS/`, unused scripts, redundant CLI shims; remove or mark deprecated with warnings + CHANGELOG entries.
  - _Acceptance Criteria_: No imports reference removed modules; CHANGELOG updated; clients unaffected.
  - _Blast Radius_: Packaging/distribution.
  - _Rollback Plan_: Restore removed assets from history.
  - _Prerequisites_: REPORT/PLAN highlight (complete M1 to ensure documentation references updated).
  - _Blockers_: Validate external consumers before removal.
  - _Status_: Planned.
- **Task M2.HEALTH.2 – Introduce app factory & module boundaries** `[tags: reliability, performance]`
  - _Goal_: Refactor `server/app.py` into `server/api/__init__.py` with routers, broadcasters, startup tasks; ensure tests cover FastAPI lifecycle.
  - _Acceptance Criteria_: `create_app()` pattern adopted; startup migration logic moved into Alembic (gated until M4); tests updated.
  - _Blast Radius_: Server runtime; high.
  - _Rollback Plan_: Revert to previous monolith.
  - _Prerequisites_: M2.TYPE.1 (typing) and M2.HEALTH.1 (cleanup) to reduce churn.
  - _Blockers_: Need migration cleanup plan (see M4.SEC). Use feature flag if necessary.
  - _Status_: Planned.

### M3 – Quality, Testing & Observability

_Objective_: Establish measurable quality gates and production-ready observability hooks while preserving existing behavior.

#### Workstream: Test Pyramid
- **Task M3.TEST.1 – Establish unit/integration/e2e markers** `[tags: testing, reliability]`
  - _Goal_: Restructure `tests/` with pytest markers, fixtures for async DB, WebSocket harness, CLI golden outputs; add coverage config.
  - _Acceptance Criteria_: `pytest -m unit`, `-m integration`, `-m e2e` run independently; coverage ≥80% on critical modules with HTML report artifact.
  - _Blast Radius_: Tests + supporting fixtures.
  - _Rollback Plan_: Revert tests/config.
  - _Prerequisites_: M1.CI.1 (CI pipeline) to consume coverage; M2 tasks ensuring stable codebase.
  - _Blockers_: None.
  - _Status_: Planned.
- **Task M3.TEST.2 – Add CLI/WebSocket integration tests** `[tags: testing, reliability, DX]`
  - _Goal_: Use `httpx.AsyncClient` + WebSocketTestClient to validate checkout/heartbeat broadcast flow; snapshot CLI transcripts.
  - _Acceptance Criteria_: Tests run deterministically; fixtures seeded; docs mention how to update snapshots.
  - _Blast Radius_: Tests only.
  - _Rollback Plan_: Remove new tests.
  - _Prerequisites_: M3.TEST.1 infrastructure.
  - _Blockers_: Need deterministic sample data seeding.
  - _Status_: Planned.

#### Workstream: Observability
- **Task M3.OBS.1 – Structured logging & correlation IDs** `[tags: observability, reliability]`
  - _Goal_: Add middleware injecting request/plan IDs, standardize JSON logging, ensure instrumentation config typed.
  - _Acceptance Criteria_: Logs include correlation IDs; docs updated; tests assert middleware behavior.
  - _Blast Radius_: Server runtime.
  - _Rollback Plan_: Feature flag to disable new middleware; revert if needed.
  - _Prerequisites_: M2.HEALTH.2 (modular app) for clean insertion.
  - _Blockers_: None.
  - _Status_: Planned.
- **Task M3.OBS.2 – Health/readiness endpoints & dashboards-as-code** `[tags: observability, reliability, docs]`
  - _Goal_: Implement `/healthz` + `/readyz`, ensure metrics endpoint via Prometheus, commit Grafana dashboards JSON + docs.
  - _Acceptance Criteria_: Endpoints pass integration tests; dashboards referenced in docs; CI smoke test hits health endpoints.
  - _Blast Radius_: Server runtime + docs.
  - _Rollback Plan_: Disable endpoints via feature flag, revert dashboards.
  - _Prerequisites_: M3.OBS.1 logging (shared middleware) and M3.TEST.1 infrastructure.
  - _Blockers_: None.
  - _Status_: Planned.
- **Task M3.OBS.3 – Trace instrumentation & OTLP exporter** `[tags: observability, performance]`
  - _Goal_: Instrument checkout/heartbeat/file upload flows with OpenTelemetry spans, enable OTLP/HTTP exporter controlled via env settings.
  - _Acceptance Criteria_: Local collector demo captures traces; CI smoke test validates exporter initialization behind feature flag; docs include troubleshooting for collector unavailability.
  - _Blast Radius_: Server runtime + docs.
  - _Rollback Plan_: Disable exporter via configuration toggle.
  - _Prerequisites_: M3.OBS.1 (logging middleware) and M2.HEALTH.2 (app factory) for instrumentation hooks.
  - _Blockers_: Availability of collector endpoints in target environments.
  - _Status_: Planned.

### M4 – Security & Supply Chain

_Objective_: Provide verifiable supply-chain integrity and harden runtime boundaries prior to broader agent adoption.

#### Workstream: Dependency Hygiene & SBOM
- **Task M4.SEC.1 – Adopt locked dependency workflow + SBOM** `[tags: security]`
  - _Goal_: Use `uv pip compile` or `pip-tools` to generate lockfiles for app/test; add Syft/CycloneDX SBOM generation in CI.
  - _Acceptance Criteria_: Lockfiles committed; CI job uploads SBOM artifact; docs explain regeneration cadence.
  - _Blast Radius_: Dependency management; medium.
  - _Rollback Plan_: Restore requirements files.
  - _Prerequisites_: M1.CI.1 pipeline to host job.
  - _Blockers_: Evaluate compatibility with deployment environment (pip/uv availability).
  - _Status_: Planned.
- **Task M4.SEC.2 – Automated dependency & secret scanning** `[tags: security, reliability]`
  - _Goal_: Add pip-audit/Safety, gitleaks, Trivy file scanning to CI + pre-commit optional stage.
  - _Acceptance Criteria_: CI fails on high severity vulnerabilities/secrets; suppression docs maintained.
  - _Blast Radius_: CI.
  - _Rollback Plan_: Disable scanning steps.
  - _Prerequisites_: M4.SEC.1 (lockfiles) for consistent dependency graph.
  - _Blockers_: Secrets scanning rate limits; monitor false positives.
  - _Status_: Planned.

#### Workstream: Configuration & Runtime Hardening
- **Task M4.SEC.3 – Pydantic settings validation + `.env.example`** `[tags: security, DX, reliability]`
  - _Goal_: Introduce typed settings module with bounds (rate limits, upload size), generate `.env.example`, update docs.
  - _Acceptance Criteria_: App fails fast on invalid config; tests cover boundary values; docs updated.
  - _Blast Radius_: Server startup configuration.
  - _Rollback Plan_: Feature flag to bypass validation.
  - _Prerequisites_: M2.TYPE.1 (typing) and M3.TEST.1 (test infra).
  - _Blockers_: None.
  - _Status_: Planned.
- **Task M4.SEC.4 – Harden file upload & auth surfaces** `[tags: security, reliability]`
  - _Goal_: Enforce upload size/content-type limits, add checksum validation, optional auth tokens.
  - _Acceptance Criteria_: Limits configurable; tests cover malicious payloads; clients documented on handling 413 responses.
  - _Blast Radius_: API + client.
  - _Rollback Plan_: Toggle limits via config or revert changes.
  - _Prerequisites_: M4.SEC.3 (config validation) and M3.TEST.2 (integration fixtures).
  - _Blockers_: Coordination with clients to handle errors.
  - _Status_: Planned.

### M5 – Performance & Resilience

_Objective_: Ensure Switchboard degrades gracefully under load and supports predictable scale-out.

#### Workstream: Runtime Resilience
- **Task M5.RES.1 – Add timeouts/retries/circuit breakers** `[tags: reliability, performance]`
  - _Goal_: Wrap outbound HTTP calls with timeouts, add retry/backoff for DB operations, circuit breaker for WebSocket broadcaster.
  - _Acceptance Criteria_: Configurable defaults; instrumentation emits retry metrics; tests simulate failure modes.
  - _Blast Radius_: Server + client runtime.
  - _Rollback Plan_: Disable via configuration feature flags.
  - _Prerequisites_: M3.OBS.1 (logging) for observability, M4.SEC.3 (config).
  - _Blockers_: None.
  - _Status_: Planned.

#### Workstream: Database & Storage Optimization
- **Task M5.RES.2 – Optimize DB schema & remove runtime DDL** `[tags: performance, reliability]`
  - _Goal_: Add indices on leases/tasks, migrate `completed_notes` column into Alembic, ensure migrations tested in CI with SQLite/Postgres matrix.
  - _Acceptance Criteria_: Alembic revision added; startup no longer mutates schema; CI migration test job green.
  - _Blast Radius_: Database schema.
  - _Rollback Plan_: Downgrade migration + revert code.
  - _Prerequisites_: M4.SEC.1 (lock dependencies) and M2.HEALTH.2 (modular app) to integrate migrations cleanly.
  - _Blockers_: Need staging environment to test migration.
  - _Status_: Planned.

#### Workstream: Benchmarking & Capacity Planning
- **Task M5.RES.3 – Introduce performance benchmarks & load profiles** `[tags: performance, testing]`
  - _Goal_: Add `pytest-benchmark` or `asv` suite for checkout/heartbeat throughput; script to produce load report.
  - _Acceptance Criteria_: Benchmarks runnable locally/CI (optional); baseline numbers stored in REPORTS/benchmarks with commentary.
  - _Blast Radius_: Tests only.
  - _Rollback Plan_: Remove benchmark suite.
  - _Prerequisites_: M3.TEST.1 infrastructure.
  - _Blockers_: CI runtime budget.
  - _Status_: Planned.

### M6 – Releases & Developer Experience

_Objective_: Deliver a polished, reproducible developer experience and automated release workflow.

#### Workstream: Release Automation
- **Task M6.REL.1 – Semantic release & package publishing** `[tags: DX, reliability]`
  - _Goal_: Configure semantic-release (or Release Please) for changelog + GitHub Releases + PyPI package, sign artifacts.
  - _Acceptance Criteria_: Release workflow generates tag, changelog, SBOM attachment, publishes to PyPI (dry run first).
  - _Blast Radius_: CI/CD.
  - _Rollback Plan_: Disable workflow, revoke tokens.
  - _Prerequisites_: M1.CI.1 (CI), M4.SEC.1 (lockfiles), M5 readiness for stable main.
  - _Blockers_: Credentials/secret storage (OIDC recommended).
  - _Status_: Planned.

#### Workstream: Developer Onboarding
- **Task M6.DX.1 – One-command bootstrap & dev loop** `[tags: DX, reliability]`
  - _Goal_: Provide `make dev`/`just dev` to start API, watchers, docker-compose dependencies; include seed data + fixtures.
  - _Acceptance Criteria_: Fresh clone can run `make dev` and reach UI within 5 minutes; docs validated.
  - _Blast Radius_: Makefile/scripts.
  - _Rollback Plan_: Revert automation scripts.
  - _Prerequisites_: Earlier milestones complete to avoid churn (tooling, tests, observability).
  - _Blockers_: OS compatibility verification.
  - _Status_: Planned.
- **Task M6.DX.2 – First hour guide & troubleshooting** `[tags: docs, DX]`
  - _Goal_: Author `docs/first-hour.md`, `docs/troubleshooting.md`, integrate with README/PLAN/STATUS references.
  - _Acceptance Criteria_: Guides reviewed, cross-linked, updated after bootstrap testing.
  - _Blast Radius_: Documentation.
  - _Rollback Plan_: Revert docs.
  - _Prerequisites_: M6.DX.1 ensures process validated.
  - _Blockers_: None.
  - _Status_: Planned.

#### Workstream: Final Audit & Hand-off
- **Task M6.DOC.1 – STATUS.md final update & recommendations** `[tags: docs]`
  - _Goal_: Summarize modernization results, outstanding risks, recommended backlog; ensure REPORT/PLAN references aligned.
  - _Acceptance Criteria_: STATUS.md updated post-final PR; links valid; final summary shared.
  - _Blast Radius_: Docs only.
  - _Rollback Plan_: Revert STATUS changes.
  - _Prerequisites_: Completion of all milestones.
  - _Blockers_: None.
  - _Status_: Planned.

---

## Cross-Cutting Dependencies & Sequencing

| Dependency | Consumes | Notes |
| --- | --- | --- |
| Governance baseline (M1.GOV.1, M1.TOOL.1) | All runtime-impacting milestones | Establishes consistent policies, tooling, and contributor expectations. |
| CI rebuild (M1.CI.1) | Typing, Testing, Security, Release | Enables matrix testing, caching, and artifact publication for later gates. |
| App factory modularization (M2.HEALTH.2) | Observability, Security, Resilience | Required to insert middleware, settings validation, and feature toggles cleanly. |
| Config validation (M4.SEC.3) | Upload hardening, resilience toggles, release automation | Ensures environments fail fast before enabling stricter guards. |

---

## Rollback Strategy Playbook
- Maintain per-task revert documentation in PR descriptions and cross-link from STATUS.md.
- Prefer additive feature flags (e.g., `ENABLE_STRUCTURED_LOGGING`, `ENABLE_UPLOAD_LIMITS`) until production soak proves stability.
- Use Alembic downgrade scripts before merging schema-affecting changes; never rely on runtime DDL.
- Keep `main` deployable: run `make qa` + targeted smoke tests locally before merging; document exceptions explicitly.
