# Global Style Guide

Last Updated: November 13, 2025

This document is a concise, drop-in style and process guide for any repository in this organization. It emphasizes reliability, maintainability, reproducibility, and security. Use this as a baseline and tailor via ADRs where justified.

---

## 0. Stack Policy (Hard Rules)

**New applications must use a TypeScript + React stack by default.**

- **UI Layer (all new apps):**
  - Must be **TypeScript + React**.
  - No new vanilla JS, jQuery, or framework-of-the-month UIs.
- **Desktop Apps:**
  - **Preferred:** Tauri (Rust + TS + React + Vite).
  - **Allowed:** Electron (Node + TS + React) when Tauri is insufficient or blocked.
- **Web Apps:**
  - SPA/PWA: React + TS + Vite.
  - SSR/ISR: Next.js (React + TS) only when SSR/SEO/edge behavior is actually needed.

**Other languages are allowed only for specific roles:**

- **Python:** AI/ML, data processing, or where a mature library ecosystem is required (e.g., scientific stack). Existing Django projects are grandfathered; no new Django apps without an ADR.
- **Rust:** Tauri shells, high-performance services, low-level engines, or systems work.
- **C#, C++:** Game engines, performance-critical modules, or platform-specific integrations.
- **C/other systems languages:** Only for kernel-adjacent, driver-like, or FFI bindings.

Any deviation from “TS + React for new app UIs” requires a short ADR explaining why.

---

## 1. Organization Constants

- **Organization**: Nobody Production  
- **GitHub Org**: Nobodyworld  
- **Maintainer**: Nobody  
- **License**: Proprietary (see LICENSE file)  
- **Solo Developer**: Yes — all repositories are maintained by a single developer  

---

## 2. Expected Stack Classifications

All repositories must declare a primary stack in `SPEC.md`. Approved primary stacks:

### 2.1 UI / App Stacks (Preferred)

- **Tauri (Preferred for Desktop)**
  - Stack: Rust + TypeScript + React + Vite
  - Use for: desktop apps needing native packaging and good perf.

- **Electron (Allowed for Desktop)**
  - Stack: Node + TypeScript + React
  - Use for: desktop apps when Tauri is blocked by ecosystem/tools.

- **React + Vite (SPA/PWA)**
  - Stack: TypeScript + React + Vite
  - Use for: browser-only apps, dashboards, admin tools, PWAs.

- **Next.js (SSR/ISR Web)**
  - Stack: TypeScript + React + Next.js
  - Use for: SEO-sensitive, SSR/ISR-heavy, or edge-deployed web apps.
  - Don’t use Next.js “just because” — justify SSR in `SPEC.md`.

### 2.2 Backend / Service Stacks

- **TypeScript Backend**
  - Node/TS (e.g. Express/Fastify/Nest or serverless functions).
  - Default choice for new CRUD-style or API services.
- **Python Service/App**
  - Role: AI/ML, data science, heavy processing, or when Python libraries are clearly superior.
  - Django/Flask/FastAPI allowed only with justification:
    - **Existing Django projects**: continue as-is; document as “legacy stack” in `SPEC.md`.
    - **New Django apps**: require an ADR with a strong reason (libraries, ecosystem, hard constraints).
- **Rust Service/CLI**
  - Role: high-performance CLI tools, background workers, or systems-level services.
- **C#/C++/C**
  - Role: engines, game runtimes, FFI bindings, or platform-specific native code.
  - UI should still be TS + React where possible (Tauri/Electron shells around these).

- **Other**
  - Any stack not listed above requires a short ADR in `docs/adr/` explaining why.

---

## 3. Core Root Files (Do Not Remove)

The following files must exist at the repository root and must not be removed:

- `README.md` — Repository overview and getting-started instructions.
- `SPEC.md` — Canonical repository specification. Keep concise and authoritative.
- `TASKLIST.md` — Single authoritative task and lightweight reporting file; one line per task; oldest-first ordering.

If any of these are missing, they must be created before substantial new work.

---

## 4. Repository Organization

Standard directories (each must include a `README.md` describing scope):

- `src/` — Source code ([src/README.md](src/README.md))
- `tests/` — Automated tests mirroring `src/` structure ([tests/README.md](tests/README.md))
- `docs/` — Documentation ([docs/README.md](docs/README.md))
- `.github/` — Workflows and templates
- `scripts/` — Developer tooling ([scripts/README.md](scripts/README.md))
- `assets/` — Small static assets (icons, images) needed at build/runtime
- `data/` — Small sample/test data only (large datasets belong in storage)

**Naming:**

- Directories: `kebab-case` (e.g., `ui-components`)
- Files (TS/JS/Rust/Go): idiomatic but consistent; e.g. `featureName.ts`, `userCard.tsx`
- Python files: `snake_case.py`
- Components/Types: `PascalCase` (e.g., `UserCard.tsx`)
- Constants: `UPPER_SNAKE_CASE`

**Binary artifacts:**

- Do **not** commit compiled binaries, archives, large images/models/datasets.
- Use Git LFS or external storage and add ignore rules.

---

## 5. Tasks and Reporting

`TASKLIST.md` is the **only** root-level task and lightweight reporting file.

Rules:

- One line per task, oldest-first.
- Include a Task Unique Identifier (e.g., `TK-YYYYMMDD-###`).
- On completion:
  - Mark `[x]`.
  - Add a short, indented sub-bullet with:
    - completion date
    - link to PR/commit
    - 1–2 line summary

Example:

- `[x] Add CI for Node/TS — TK-2025-10-29-001`  
  - `Completed: 2025-11-01 — PR: https://github.com/org/repo/pull/123 — Added check-only lint/test workflows.`

Deprecated: `REPORTS.md`, `TASK.md`, and other ad hoc task files. Do not create new ones.

For long-form post-mortems or reports, put them in `docs/` and link from `TASKLIST.md`.

---

## 6. Code Quality Standards (Polyglot)

### **Formatting & linting**

- **TypeScript/React**
  - Prettier + ESLint (`typescript-eslint`)
  - Strict TypeScript (`"strict": true`); avoid `any`.
- **Python**
  - Black + Ruff + isort
- **Rust**
  - `rustfmt` + `clippy`
- **Shell**
  - `shfmt` + `shellcheck`

### **Error handling**

- No silent failures.
- Prefer typed/structured errors with context.
- For I/O: timeouts, retries with backoff, and circuit breakers.

### **Logging**

- Use structured logs where reasonable (JSON fields).
- Avoid PII in logs.
- Include correlation/trace IDs for multi-step flows.

### **Imports**

- Order: stdlib → third-party → local.
- Remove unused imports/exports aggressively.

### **Dependencies**

- Prefer small, well-maintained libraries.
- Remove unused deps regularly.
- Pin/tool versions where appropriate.

### 6.1 TypeScript/React specifics

- Use functional components and hooks.
- Clean up effects (`useEffect`) properly.
- Define typed props/interfaces; stable component APIs.
- Accessibility:
  - Keyboard support
  - Labels for form controls
  - Focus management
  - WCAG-aligned contrast

### 6.2 Python specifics

- Use type hints.
- Docstrings (Google or NumPy style).
- Explicit virtualenv.
- Deterministic tests.

### 6.3 Rust specifics

- Use `Result` with context (`anyhow` or custom errors).
- Keep modules small and focused.
- Trait-based boundaries; avoid giant god-modules.

---

## 7. Testing Strategy

- Favor: unit > integration > e2e (pyramid, not ice cream cone).
- Naming:
  - JS/TS: `*.test.ts` / `*.spec.ts`
  - Python: `test_*.py`
  - Rust: `*_test.rs`
- Tests should be:
  - Fast
  - Deterministic
  - Hermetic (no hidden external dependencies)
- Mock external I/O; freeze time/randomness where needed.
- Prioritize tests for:
  - Core logic
  - Data transformations
  - Critical regressions

---

## 8. Configuration & Environments

- Use environment variables for secrets and environment-specific settings.
- Document env vars in `README.md` (required vs optional, defaults).
- Validate env vars at startup.
- Use `*.example` files to show config structure and keep actual secrets out of VCS.
- Separate **build-time** and **runtime** config clearly.

---

## 9. Documentation

Minimum:

- `README.md` with:
  - Overview
  - Setup
  - Development
  - Testing
  - Release
  - Troubleshooting
  - Support/contact

Inline docs:

- Public APIs: TSDoc/JSDoc, Python docstrings, Rust doc comments.
- Complex logic: brief comments explaining rationale and invariants.

Architecture & APIs:

- ADRs for major decisions (`docs/adr/`).
- Use diagrams (e.g., Mermaid) when helpful.

---

## 10. Security & Compliance

- Validate inputs; encode outputs.
- Principle of least privilege (APIs, DB, file access).
- Secret management via env/secret stores; no secrets in code or history.
- CI should include:
  - Secret scans
  - SAST/lint checks
  - Dependency vulnerability scans
- For UIs, aim for WCAG 2.1 AA accessibility.

---

## 11. Performance & Reliability

- Set lightweight budgets:
  - Bundle size
  - Latency
  - Memory usage (where relevant)
- Frontend:
  - Code-splitting
  - Lazy-loading
  - Asset optimization
  - Caching
- Backend:
  - Timeouts on external calls
  - Idempotent retries
  - Indexed queries
  - Health checks / readiness probes

---

## 12. CI/CD

- CI must run (at minimum):
  - Format
  - Lint
  - Typecheck
  - Tests
  - Security checks (where applicable)
- Prefer reusable org workflows (`workflow_call`) where possible.
- Keep pipelines fast with caching.
- Releases:
  - Semantic versioning
  - Changelog updates
  - Rollback plan
  - Feature flags when feasible

---

## 13. Collaboration & Process

- Branch naming:
  - `feat/...`, `fix/...`, `chore/...`, `docs/...`, `refactor/...`
- Conventional Commits for messages.
- Small, reviewable PRs with clear scope.
- All work should map to an issue or a `TASKLIST.md` entry.
- Keep docs and READMEs updated as part of the same PR when behavior changes.

---

## 14. Exceptions & Legacy Code

- Any deviation from:
  - **TS + React as default UI**, or
  - **Approved stacks in Section 2**

  must have an ADR with:
  - Reason
  - Impact
  - Long-term plan (keep vs migrate).

- Legacy projects (e.g., existing Django apps) must:
  - Mark their status in `SPEC.md` as `legacy-stack: true`.
  - Either:
    - Be maintained as-is with minimal churn, or  
    - Have a gradual migration plan documented.

---

## 15. Continuous Improvement

- Track over time (where practical):
  - Test coverage
  - Performance metrics
  - Security issues
  - Defect rates
- Periodically:
  - Review toolchains
  - Clean dependencies
  - Improve templates and bootstrap scripts
- Use retrospectives on significant issues to feed back into this guide.
