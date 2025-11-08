# Global Style Guide

Last Updated: November 03, 2025

This document is a concise, drop-in style and process guide for any repository in this organization. It emphasizes reliability, maintainability, reproducibility, and security. Use this as a baseline and tailor via ADRs where justified.

## Organization Constants

- **Organization**: Nobody Production
- **GitHub Org**: Nobodyworld
- **Maintainer**: Nobody
- **License**: Proprietary (see LICENSE file)
- **Solo Developer**: Yes - all repositories are maintained by a single developer

## Expected Stack Classifications

All repositories should use one of the following primary stacks:

- **Tauri** (Rust + TypeScript + React + Vite) - Preferred for desktop apps with web UI
- **Electron** (Node + TypeScript + React) - For complex desktop applications
- **React + Vite** (SPA/PWA) - For web applications
- **Next.js** (SSR/ISR) - For server-rendered web apps
- **Python service/app** - For backend services and data processing
- **Rust CLI/service** - For high-performance CLI tools and services
- **Other** - Document justification in SPEC.md

## 0. Core Root Files (Do Not Remove)

- **NEVER REMOVE** `README.md`, `SPEC.md`, or `TASKLIST.md` from the repository root.

- Purposes:
  - `README.md` — Repository overview and getting-started instructions.
  - `SPEC.md` — Canonical repository specification. Keep concise and authoritative.
  - `TASKLIST.md` — The single authoritative task and lightweight reporting file for the repo; one line per task; oldest-first ordering.

## 1. Repository Organization

- Typical directories (each must include a README describing scope)
  - `src/` — source code ([src/README.md](src/README.md))
  - `tests/` — automated tests mirroring `src/` structure ([tests/README.md](tests/README.md))
  - `docs/` — documentation ([docs/README.md](docs/README.md))
  - `.github/` — workflows and templates
  - `scripts/` — developer tooling ([scripts/README.md](scripts/README.md))
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

## 1.1 Tasks and Reporting (Consolidated)

We standardize on a single file for tasks and lightweight reporting: `TASKLIST.md`.

- TASKLIST.md rules
  - Keep tasks one line each; oldest first; check off when done.
  - Include a Task Unique Identifier (e.g., `TK-YYYYMMDD-###`).
  - When a task is completed, update the task line to indicate completion and append a brief report as an indented sub-bullet containing:
    - completion date, PR or link to changes, short summary (1–2 lines).
  - Example:
    - `- [x] Add CI for Node/TS — TK-2025-10-29-001`
      - `Completed: 2025-11-01 — PR: https://github.com/org/repo/pull/123 — Added check-only lint/test workflows.`

### Notes

- `REPORTS.md` and `TASK.md` are deprecated. Do not create or rely on them. Keep all task state and lightweight reports inside `TASKLIST.md` so reviewers and automation only need to look in one place.

- For long-form post-mortems or extensive reports, link to a `docs/` file from the TASKLIST entry rather than creating a separate ad-hoc task/report file in the repo root.

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
  - Use appropriate observability libraries for CLI and automation surfaces; wrap long-running operations in tracing spans.
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
- Go
  - Use `gofmt`; follow effective Go guidelines; error handling with explicit returns; keep packages small and focused.

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

- Planning docs: keep high‑level plan in `SPEC.md`; decisions via ADRs.
- Tasks: ONLY `TASKLIST.md` (one per active directory). No other TODO files in the repo root — keep all task state here.
- Outputs: paste check‑only results into PRs and update `TASKLIST.md` with completion details and a PR link.
- Reporting: include short completion notes inline in `TASKLIST.md` (see 1.1). For longer reports, add a document under `docs/` and link to it from the task entry.

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
