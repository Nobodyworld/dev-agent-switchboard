# Add read-only operator readiness and bounded live progress

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Make the newly merged trusted validation lifecycle easier to operate without expanding its authority. A trusted operator should be able to answer three questions from supported CLI surfaces: whether an exact configuration is currently ready to run, what phase an approved lifecycle is actually in, and what bounded corrective action is appropriate when readiness or execution fails.

The slice adds a read-only `validation-preflight` command, truthful bounded lifecycle progress, actionable diagnostics, clean human versus JSON output, and a clearer stored-runtime inspection notice. It must reuse the existing execution preflight, lifecycle, report, and CLI architecture. It must not create another executor, turn readiness into approval, weaken explicit approvals, add automatic retry/fixing, or claim production readiness.

Classification remains `PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY`.

## Progress

- [x] PR #152 squash-merged to `main` as `78ff87a87e2322f6a77732b5b0368c4379dc0b62`.
- [x] Resulting-main Workload acceptance passed.
- [x] Resulting-main CI run `34146946641` passed.
- [x] Issue #151 closed as completed.
- [x] Issue #157 accepted as the successor contract.
- [x] Canonical branch `feat/operator-readiness-progress` created from exact merged main.
- [x] Living ExecPlan created.
- [ ] Record current CLI/output behavior from the exact branch before implementation.
- [ ] Implement read-only readiness using the authoritative execution preflight.
- [ ] Implement optional bounded lifecycle progress observation without changing authority.
- [ ] Implement human and machine output separation plus reviewed diagnostics.
- [ ] Make stored inspection visibly state that live evidence is not reverified.
- [ ] Update CLI tests, lifecycle/preflight regressions, README, operator guide, and moving status.
- [ ] Run focused validation, both synthetic lifecycle modes over IPv4/IPv6, Windows-specific regressions where available, and complete repository gates.
- [ ] Push exact branch state normally and record local/remote parity.
- [ ] Reconcile hosted checks and connector review.
- [ ] Leave the implementation PR draft and unmerged pending separate owner authorization.

## Surprises & Discoveries

- Observation: No standalone readiness command exists on merged main; `scripts/dev.py validation-lifecycle` performs preflight only as the first execution phase and `inspect-validation-runtime` reports stored state.
  Evidence: Source inspection of `scripts/dev.py` and issue #157 preparation at the predecessor head; the merged tree is the same validated source tree.

- Observation: Lifecycle phases are already authoritative ordered state in the execution operator, so progress should observe those transitions rather than infer work from elapsed time, queue creation, or presentation-side state.
  Evidence: Existing lifecycle report phase contract and issue #157 acceptance language.

## Decision Log

- Decision: Reuse the same preflight implementation used immediately before execution and expose only a read-only result model around it.
  Rationale: A second readiness implementation could drift from execution and create false confidence. Execution must still rerun preflight because readiness is only a point-in-time observation.
  Date/Author: 2026-09-07 / ChatGPT connector preparation

- Decision: Add progress as an optional observer/presentation hook on existing lifecycle transitions, not as a new execution state machine.
  Rationale: Progress must never become authoritative evidence or change approval, cleanup, or failure semantics.
  Date/Author: 2026-09-07 / ChatGPT connector preparation

- Decision: Machine-readable mode owns stdout as one bounded JSON object; prompts and progress use stderr.
  Rationale: This gives scripts a stable parseable channel without suppressing fail-closed approval behavior or mixing human messages into JSON.
  Date/Author: 2026-09-07 / ChatGPT connector preparation

- Decision: Do not fold dependency PRs #153-#156 or workspace-hygiene PR #148 into this feature branch.
  Rationale: #157 is an operator-usability slice with an already locked scope; dependency/runtime changes would confound validation and review.
  Date/Author: 2026-09-07 / ChatGPT connector preparation

## Outcomes & Retrospective

Not yet implemented. The intended outcome is one coherent operator-usability improvement: readiness before mutation, truthful progress during execution, and bounded actionable results afterward, with no new execution authority.

## Context and Orientation

Authoritative issue: GitHub #157, `feat(operator): add read-only readiness and bounded live progress`.

Exact implementation base: merged `main` `78ff87a87e2322f6a77732b5b0368c4379dc0b62`, the squash result of PR #152. Resulting-main CI `34146946641` and Workload acceptance `34146946670` passed.

Key files and interfaces:

- `scripts/dev.py` — existing developer CLI, including `validation-lifecycle` and `inspect-validation-runtime`.
- `client/python/execution_operator/config.py` — strict bounded operator configuration parsing and validation.
- `client/python/execution_operator/preflight.py` — authoritative exact source/manifest/tool/root/port/token/timeout preflight used by execution.
- `client/python/execution_operator/lifecycle.py` — supported lifecycle orchestration and ordered phase recording.
- `client/python/execution_operator/models.py` — lifecycle and stored-inspection report models and safe serialization.
- `client/python/execution_operator/report_contract.py` — strict report consistency contract.
- `client/python/tests/test_execution_operator.py` — core lifecycle/preflight tests.
- `client/python/tests/test_execution_operator_corrections.py` — trust-boundary and report/read regressions added during #151.
- `docs/operations/operator-validation-lifecycle.md` — operator-facing lifecycle procedure and boundaries.
- `README.md` — supported top-level operator path.
- `docs/reports/status.md` — mutable project status; update current state without rewriting historical evidence.

Preserve issue #146/#149 historical worktrees, successful and failed retained evidence, historical runtimes/reports, and `security-deferral-wip`. No cleanup is part of #157.

## Plan of Work

1. Establish the exact behavior baseline on the prepared branch before editing. Record how `validation-lifecycle` writes approvals/final output, how non-interactive approval denial behaves, and how `inspect-validation-runtime` presents stored state. Keep machine paths and private data out of GitHub evidence.

2. Refactor preflight only as needed to expose a reusable bounded result without weakening the existing fail-closed execution path. Add `validation-preflight --config <private-json>` to `scripts/dev.py`. It must use the same checks execution uses, create no runtime or execution state, and identify checks that were not performed because an earlier prerequisite failed rather than marking them passed.

3. Define a small readiness result contract that contains only safe logical identity, stable check/failure codes, configured versus required timeout facts where useful, and checked/not-checked/pass/fail state. Keep private paths, raw Git output, argv, environment values, token values, HTTP bodies, and raw exceptions out of both human and machine output.

4. Add an optional progress observer to the existing lifecycle implementation. Emit only transitions that have actually occurred or authoritative states that were actually observed. Cover startup, both approval boundaries, work-order/run observation, evidence verification, shutdown, and cleanup. Preserve existing library callers when no observer is supplied.

5. Make presentation failure non-authoritative. An observer or output exception must never grant approval, fabricate lifecycle state, trigger retry, suppress owned cleanup, or convert a failed lifecycle into success. Prefer bounded best-effort presentation while authoritative execution continues its required shutdown path.

6. Add explicit human and machine modes to relevant CLI surfaces. In machine mode stdout must contain exactly one documented JSON result on success or failure. Prompts, progress, and human diagnostics go to stderr. Non-interactive execution without deliberate approval must fail closed without hanging.

7. Map existing bounded reason codes to concise reviewed operator guidance for common failures: missing process token, unavailable runtime/tool, dirty or wrong source, unsafe/existing runtime root, occupied port, manifest/worker timeout mismatch, and terminal observation budget mismatch. Guidance may tell the operator what category to correct but must not run a fix automatically or echo unsafe source values.

8. Improve stored runtime inspection presentation so human output clearly states `stored state only; live evidence not reverified`. Preserve the existing stored JSON contract and never rewrite historical records.

9. Add focused tests proving side-effect-free readiness, same-check parity with execution, stale-readiness rejection at actual execution, bounded progress ordering, approval boundaries, output-channel separation, observer failure safety, safe diagnostics, historical report compatibility, and inspection labeling.

10. Rerun the established synthetic fresh-only and fresh-then-exact-reuse paths on IPv4 and IPv6. Retain the existing Windows junction, marker ownership, cancellation, preservation, process shutdown, port release, security, browser, and coverage gates. Report genuine platform skips explicitly.

11. Update `README.md`, `docs/operations/operator-validation-lifecycle.md`, and `docs/reports/status.md` as part of the substantive implementation. Reconcile stale moving references to #151/#152 without changing immutable historical evidence.

## Concrete Steps

From the local continuation worktree:

1. Verify repository identity, common Git directory, worktree inventory, branch/upstream, clean status, and exact starting SHA. Do not work from `main`.
2. Read `PROJECT_RULESET.md`, root/scoped `AGENTS.md`, `.agent/PLANS.md`, this ExecPlan, and issue #157.
3. Record the current CLI behavior using safe temporary inputs owned by the slice; do not publish private paths or credentials.
4. Implement the feature in small reviewed commits on `feat/operator-readiness-progress`.
5. Run focused tests while developing.
6. Run the complete repository validation required by the ruleset and #157, including strict browser/security/coverage gates and the lifecycle matrix.
7. Inspect worktree/process/port/runtime side effects and reconcile only slice-owned temporary state under repository rules. Preserve all pre-existing state.
8. Push normally; no force push or rebase. Return exact local/remote parity and validation evidence for connector review.

## Validation and Acceptance

Acceptance is the complete contract in issue #157. At minimum prove:

- `validation-preflight` success uses the same authoritative checks as execution and leaves no runtime/database/server/worker/work-order/report side effects.
- Representative configuration, source, tool, root, port, token, and timeout failures return bounded safe statuses; dependent unperformed checks are not represented as passed.
- A successful readiness observation does not authorize execution or reserve state; source dirtiness or port occupation introduced after readiness is caught when execution reruns preflight.
- Progress follows actual observed transitions, respects fresh and reuse approvals, remains bounded, and cannot fabricate completion or cleanup.
- Observer/output failure cannot bypass approval or prevent required owned cleanup.
- Machine mode stdout is exactly one JSON object on both success and failure; human/progress text stays off that channel.
- Stored inspection visibly communicates that live evidence was not reverified while preserving schema-2 historical report compatibility.
- Both synthetic lifecycle modes still pass on IPv4 and IPv6.
- Relevant Windows junction/process/path/port regressions pass where the environment supports them; platform-specific skips are enumerated truthfully.
- Full local verification and exact-head hosted checks pass without reducing any threshold or security gate.

Do not require a new unrelated full live external-target campaign solely to satisfy bookkeeping.

## Idempotence and Recovery

Readiness is designed to be repeatable and read-only but is not cacheable authorization. It may safely be rerun; execution always performs a fresh preflight.

If local branch/worktree state differs from the expected continuation, stop and report rather than reset, clean, stash, rebase, recreate the branch, or create a parallel implementation. Preserve unknown or pre-existing work.

If implementation or validation fails, keep the branch and slice-owned worktree for diagnosis. Do not weaken tests, delete historical runtimes/evidence, or repair previous reports to make validation pass.

## Artifacts and Notes

Remote preparation evidence:

- implementation base: `78ff87a87e2322f6a77732b5b0368c4379dc0b62`
- resulting-main CI: `34146946641` — success
- resulting-main Workload acceptance: `34146946670` — success
- predecessor issue #151: closed completed
- successor issue: #157
- branch: `feat/operator-readiness-progress`

Local logs, machine paths, credentials, temporary runtime roots, and complete artifact bytes remain private. GitHub evidence must stay bounded and sanitized.

## Interfaces and Dependencies

Expected public/internal interfaces after implementation:

- `python scripts/dev.py validation-preflight --config <private-json>`
- existing `python scripts/dev.py validation-lifecycle --config <private-json>` with optional bounded progress/machine presentation while preserving approval semantics
- existing `python scripts/dev.py inspect-validation-runtime <runtime-root>` with explicit human stored-state-only notice and compatible machine JSON
- one reusable readiness result contract backed by the same preflight checks as execution
- one optional lifecycle observer interface that receives bounded authoritative transition events and is absent by default for library callers

No new third-party dependency is expected. Any proposed dependency addition, credential model, isolation architecture, MCP/tunnel, worker type, workload, source-write authority, retry/repair engine, deployment, release, or production claim is out of scope and requires separate owner approval.