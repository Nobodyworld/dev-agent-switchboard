# Global Style Guide

This document is a concise, drop-in style and process guide for any repository in this organization. It emphasizes reliability, maintainability, reproducibility, and security. Use this as a baseline and tailor via ADRs where justified.

## 0. Core Root Files (Do Not Remove)

- NEVER REMOVE: `TASK.md`, `TASKLIST.md`, `REPORTS.md`, or `URGENT.md` from the repository root.
- Purposes
  - `URGENT.md` — high-level plan, repo snapshot, agent quickstart, risks, and DoD.
  - `TASKLIST.md` — the only task tracker; one line per task; oldest-first ordering.
  - `REPORTS.md` — chronological PR log; one entry per PR with cross-links to tasks.
  - `TASK.md` — optional scratchpad for task details (final tasks must live in `TASKLIST.md`).

## 1. Repository Organization

- Typical directories
  - `src/` — source code
  - `tests/` — automated tests mirroring `src/` structure
  - `docs/` — documentation (README(s), ADRs, diagrams)
  - `.github/` — workflows and templates
  - `scripts/` — developer tooling (idempotent, cross‑platform when possible)
  - `assets/` — small static assets (icons, images) needed at build/runtime
  - `data/` — small sample/test data only (large datasets belong in storage)
- Naming
  - Directories: `kebab-case` (e.g., `ui-components`)
  - Files (JS/TS/Go/Rust): `camelCase.ts|.go|.rs` where idiomatic; Python: `snake_case.py`
  - Components/Types: `PascalCase` (e.g., `UserCard.tsx`)
  - Constants: `UPPER_SNAKE_CASE`
- Binary artifacts
  - Do not commit compiled binaries, archives, large images/models/datasets.
  - Use Git LFS or external object storage and add ignore rules.

## 1.1 Tasks and Reports Conventions (Cross‑linking)

- TASKLIST.md
  - Keep tasks one line each; oldest first; check off when done.
  - Include a Task Unique Identifier (e.g., `TK-YYYYMMDD-###`).
  - On completion, append: completion timestamp and hyperlink to the matching REPORTS.md entry (Task Report Unique Identifier).
  - Example:
    - `- [ ] Add CI for Node/TS — TK-2025-10-29-001 — When completed: 2025-11-01, link: REPORTS.md#TR-2025-11-01-003`
- REPORTS.md
  - Append one entry per PR in chronological order.
  - Include fields: Task Report Unique Identifier (e.g., `TR-YYYYMMDD-###`), Task Unique Identifier (link back to `TASKLIST.md`), Description, References, Problems Solved, Next Steps.
  - Example heading:
    - `### 2025-11-01 - chore(ci): add node checks (https://github.com/org/repo/pull/123)`
    - Then include: `Task Report Unique Identifier: TR-2025-11-01-003` and `Task Unique Identifier: TK-2025-10-29-001` with links.
  - Never overwrite past entries; always append.

## 2. Code Quality Standards (Polyglot)

- Formatting & linting
  - JS/TS: Prettier + ESLint (typescript‑eslint)
  - Python: Black + Ruff + isort
  - Rust: rustfmt + clippy
  - Shell: shfmt + shellcheck
- Error handling
  - No silent failures; return typed/structured errors with context.
  - Add timeouts, retries with backoff, and circuit breakers for I/O.
- Logging
  - Structured logs (JSON fields where possible); avoid PII; include correlation/trace IDs.
- Imports
  - Order: stdlib → third‑party → local; avoid unused imports/exports.
- Dependencies
  - Prefer small, well‑maintained libraries; remove unused deps; pin/tool versions where appropriate.

### Language specifics

- TypeScript/React
  - Functional components; hooks for reusable logic; effect cleanups required.
  - Strict TS; avoid `any`; define props/interfaces; aim for stable component APIs.
  - Accessibility: keyboard support, labels, focus management, color contrast.
- Python
  - Type hints; docstrings (Google or NumPy style); explicit virtualenv; deterministic tests.
- Rust
  - Prefer `Result` with context via `anyhow`/custom errors; small modules; trait‑based boundaries.

## 3. Testing Strategy

- Pyramid: unit > integration > e2e; fast, deterministic, hermetic tests.
- Naming: `.test.*`/`.spec.*` (JS/TS), `test_*` (Py), `*_test.rs` (Rust).
- Coverage: target meaningful coverage; prioritize critical paths and regressions.
- Mocks: isolate external I/O; freeze time/randomness.

## 4. Configuration & Environments

- Environment variables
  - Document in `README` with required/optional flags and sane defaults.
  - Validate at startup; never commit secrets.
- Separation
  - Distinguish build vs runtime config; keep local overrides out of VCS with `*.example` files.

## 5. Documentation

- README (at least): Overview, Setup, Development, Testing, Release, Troubleshooting, Support.
- Inline docs
  - Public APIs require doc comments (JSDoc/TSDoc, Python docstrings, Rust doc comments).
  - Comment complex logic with rationale and invariants; keep comments current.
- Architecture & APIs
  - Maintain ADRs for significant decisions; include diagrams (e.g., Mermaid) as helpful.

## 6. Security & Compliance

- Input validation, output encoding, and least privilege by default.
- Secret management via environment/secret stores; no credentials in code or history.
- Automated scanning in CI (secrets, SAST, dependency vulns, license checks).
- Privacy & accessibility: follow data handling policies and WCAG 2.1 AA for UIs.

## 7. Performance & Reliability

- Set lightweight budgets (bundle size, latency, memory) and track in CI/monitoring.
- Frontend: code‑split; lazy load; optimize assets; cache wisely.
- Backend: timeouts on external calls; idempotent retries; index queries; health checks.

## 8. CI/CD

- Check‑only by default: format/lint/typecheck/test/security must run in CI.
- Reuse organization workflows where available (`workflow_call`); keep pipelines fast and cached.
- Releases: semantic versioning; changelog updates; rollback plan; feature flags when feasible.

## 9. Collaboration & Process

- Branch naming: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`.
- Conventional Commits; small, reviewable PRs with clear scope and checklist.
- Code reviews: required; use a short, consistent checklist.
- Issue tracking: all work via issues; keep docs/README updated with changes.

## 10. Planning & Tasks

- Planning docs: keep high‑level plan in `URGENT.md`; decisions via ADRs.
- Tasks: ONLY `TASKLIST.md` (one per active directory). No other TODO files.
- Outputs: paste check‑only results into PRs and check off tasks as completed.
- Cross‑linking: every completed task must link to a `REPORTS.md` entry; every `REPORTS.md` entry must cite the task it fulfilled.

## 11. Exceptions

- Deviations from this guide require an ADR (or equivalent) with rationale, impact, and a plan to reconcile or permanently diverge.

## 12. Continuous Improvement

- Track: test coverage, performance metrics, security findings, defect rates.
- Retrospectives for process updates; periodic toolchain reviews; ongoing training.

---

Appendix: Tooling References

- TypeScript: eslint, typescript‑eslint, prettier, vitest/jest
- Python: ruff, black, isort, pytest
- Rust: rustfmt, clippy, cargo test
- Shell: shfmt, shellcheck
- Diagrams: Mermaid (in Markdown)
