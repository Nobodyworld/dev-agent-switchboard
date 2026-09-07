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
- [x] Verify origin, common Git directory, clean primary state, prepared remote head and base, preserved worktree/runtime inventory, and existing stash. Create the sole successor worktree tracking the prepared branch; preserve the older primary checkout unchanged.
- [x] Record current CLI/output behavior from the exact branch before implementation.
- [x] Implement read-only readiness using the authoritative execution preflight.
- [x] Implement optional bounded lifecycle progress observation without changing authority.
- [x] Implement human and machine output separation plus reviewed diagnostics.
- [x] Make stored inspection visibly state that live evidence is not reverified.
- [x] Update CLI tests, lifecycle/preflight regressions, README, operator guide, and moving status.
- [x] Run focused validation, both synthetic lifecycle modes over IPv4/IPv6, Windows-specific regressions where available, and complete repository gates; enumerate genuine skips and invalid initial harness attempts below.
- [ ] Push exact branch state normally and record local/remote parity.
- [ ] Reconcile hosted checks and connector review.
- [ ] Leave the implementation PR draft and unmerged pending separate owner authorization.

## Surprises & Discoveries

- Observation: The initial concurrent full pytest and verification invocations had different pytest temporary roots but still shared the server fixture's default SQLite file in the new worktree. Once both reached server tests, setup/teardown errors appeared. Both incomplete invocations were stopped and their processes verified exited; the slice-owned database and temporary state were retained. This is invalid test-harness isolation, not evidence of an operator regression or a passing gate.
  Evidence: `server.db.DEFAULT_DATABASE_URL` and the server fixture's per-case table reset. Replacement validation invocations explicitly use different task-owned database, storage, file, pytest, and coverage paths. No preserved database was opened or modified, and no product/test change was made to accommodate the harness error.

- Observation: A bounded presentation still needs complete identity validation. Review reproduced a credential collision with the manifest digest that would otherwise make a ready result fail during serialization. Shared preflight now rejects unsafe configured identity before probes and an unsafe verified digest at the manifest check, using closed failure reasons.
  Evidence: Focused readiness identity/credential-collision regressions; successful readiness requires complete safe identity and consistent timeout/digest facts.

- Observation: Unexpected output errors and interruption at the readiness CLI originally escaped a one-object machine result in the first implementation draft. The command now emits a sanitized command-error object when the output channel is usable. A broken stdout cannot deliver JSON; it exits unsuccessfully after execution has performed its shutdown, with best-effort safe stderr only.
  Evidence: Focused CLI exception, broken-prompt, stdout-failure, independent-approval, and stored-report byte/timestamp regressions.

- Observation: At prepared head `44091095fadaf5601ec9e5cf26b13669606742c5`, command help contains no readiness surface. Missing lifecycle configuration and missing inspection runtime both exit 1 with human failure text on stdout. Source inspection shows approval prompts also use stdout, while successful lifecycle and inspection use the schema-2 JSON report. Non-interactive input without the corresponding approval flag is already denied.
  Evidence: Read-only help/missing-input probes in the existing pinned Python 3.11.14 environment, plus `cmd_validation_lifecycle` and `cmd_inspect_validation_runtime` inspection before edits. No runtime or work order was created by these probes.

- Observation: `StoredOperatorLifecycleReport.as_text()` already contains the required stored-state warning, but the CLI only called its JSON serializer.
  Evidence: The existing stored report class and inspection command on the prepared head.

- Observation: No standalone readiness command exists on merged main; `scripts/dev.py validation-lifecycle` performs preflight only as the first execution phase and `inspect-validation-runtime` reports stored state.
  Evidence: Source inspection of `scripts/dev.py` and issue #157 preparation at the predecessor head; the merged tree is the same validated source tree.

- Observation: Lifecycle phases are already authoritative ordered state in the execution operator, so progress should observe those transitions rather than infer work from elapsed time, queue creation, or presentation-side state.
  Evidence: Existing lifecycle report phase contract and issue #157 acceptance language.

## Decision Log

- Decision: Keep lifecycle and inspection default successful JSON shapes unchanged, add explicit `--format human|json`, and make new readiness default to human output. Prompts and optional progress use stderr. Inspection JSON remains the historical report unchanged and carries its scope notice on stderr.
  Rationale: Existing JSON consumers and schema-2 retained reports stay compatible while human users gain a supported presentation. Configuration and argument failures receive fixed sanitized diagnostics rather than raw values.
  Date/Author: 2026-09-07 / Codex implementation

- Decision: Use an optional bounded observer with closed event vocabulary; callback failure disables presentation while execution retains its existing approval and ownership checks.
  Rationale: Output is an observation channel. Its exceptions cannot authorize work, cause a retry, or suppress owned shutdown.
  Date/Author: 2026-09-07 / Codex implementation

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

The implementation adds readiness before mutation, actual observed progress during execution, and reviewed corrective guidance. Both execution and readiness use the same eleven-check assessment; the existing execution return type and schema-2 stored reports remain compatible. Readiness has a fixed schema-1 result capped at 16 KiB, with fail-fast check state and exact safe identity/timeout facts. Git probes disable optional metadata locks/refresh writes.

An optional observer receives at most 64 deduplicated closed events, including separate request/approval/queue/run/evidence transitions. It never infers running from queuing, and completion follows report persistence. Callback exceptions disable only presentation. Existing approval and immutable marker ownership continue to govern execution and cleanup.

Lifecycle/inspection JSON success remains the existing report object. New readiness defaults to human output, with explicit JSON available. Prompts/progress use stderr. Human inspection uses the existing stored-state warning; JSON inspection keeps the stored document unchanged and emits that notice on stderr. Runtime reports are neither rewritten nor upgraded by inspection.

Local implementation and repository validation are complete at this pre-publication checkpoint. The corrected isolated full runs both passed, with platform/runtime skips recorded below and no reduced gates. Final code identity, normal-push parity, exact-head hosted checks and connector review are subsequent delivery gates; their live result belongs in draft PR #158 and the delivery report so a self-referential documentation commit does not invalidate its own SHA. Owner authorization remains separate.

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

Local validation record (2026-09-07, implementation tree based on prepared head `44091095fadaf5601ec9e5cf26b13669606742c5`):

- The sole successor worktree tracks `origin/feat/operator-readiness-progress`. Initial local and remote feature heads matched the prepared head; remote main matched `78ff87a87e2322f6a77732b5b0368c4379dc0b62`. The clean older primary checkout was preserved, not advanced. All historical worktrees, named runtime/evidence roots, and the security-deferral stash were present and left untouched.
- Existing Windows Python 3.11.14 environment; pytest 9.1.1, Mypy 1.18.2, Ruff 0.16.2, Bandit 1.9.4, coverage 7.16.0, and pip-audit 2.10.1. Exact cached pnpm 10.18.1 was selected through existing task-local infrastructure; host-default pnpm and settings were unchanged. Local Node 24.19.0 satisfies the project floor; hosted CI separately pins Node 24.12.0. No dependency or workload definition changed.
- Focused operator, corrections, readiness, progress, and CLI matrix: 246 passed, 6 explicitly skipped. All four real server/worker synthetic combinations (fresh-only and fresh-then-exact-reuse, each on IPv4 and IPv6) passed with separate target source, readiness before runtime creation, independent approvals, observed progress, retained-evidence proof, unchanged canonical state, stopped owned processes, released port, and empty worker source.
- Standalone strict Playwright: 4 passed, zero skipped. Strict browser mode is also enabled in the full pytest and verification suites.
- Isolated full pytest passed: 979 passed, 18 skipped, one existing Starlette/httpx deprecation warning, in 1131.31 seconds. The skips are seven unavailable Windows symlink creations, eight explicitly POSIX/Linux-only cases, two real-worker profiles requiring Python 3.12+/3.13+, and one explicitly gated full-manifest operator exercise. The four strict browser cases passed with zero browser skips. No skip predicate or dependency was changed.
- Complete `python scripts/dev.py verify` passed: Ruff, strict Mypy, Bandit, 979 passed / 18 skipped / one warning in its 1202.17-second coverage suite, all 20 configured thresholds, and environment pip-audit with no known vulnerabilities. Aggregate measured coverage was 2745/3050 statements (90.00%). A separate invocation enforced all 22 CI module thresholds, including interfaces and task service, without changing their values. New diagnostics and progress modules measured 100%; readiness measured 97.17%.
- The focused, full-pytest, and verification artifacts each contain the same four passing mode/host integrations, giving three complete successful matrix repetitions. Both full artifacts contain all four strict browser cases with no browser skip. Full native Windows evidence includes four real parent/child cancellation cases, eight real junction cases, and six passing strict-containment tests (three Linux-only cases skipped). Each lifecycle matrix asserts unchanged target state, zero active leases/runs, stopped owned processes, bindable released ports, and empty worker source before successful test-owned runtime finalization.
- Ruff lint, Ruff format (329 files unchanged), strict Mypy (207 source files on both Windows and Linux target platforms), and all-file pre-commit passed. Pre-commit Black checked the explicitly selected Python files; standalone `black --check .` exits zero but selects no files under the existing escaped include expression. Prettier likewise has no applicable hook files under the existing configuration. Those selector limitations are not represented as independent formatting proof and were not changed in this slice.
- Bandit passed with existing redundant `nosec` warnings only. Requirements-file pip-audit found no known vulnerabilities. An initial sandbox audit bootstrap stalled; its exact process tree was stopped and verified exited before a task-local, noninteractive elevated run passed. No project or host package was changed.
- Workload catalog validation passed for all four repositories; TODO policy passed; all four tracked JavaScript files passed Node syntax; three TOML and fourteen YAML files parsed; all twenty-five Action references across three workflows are full-SHA pinned. Detect-secrets passed in pre-commit; Gitleaks found no leaks in the 349-commit pre-publication history.
- The separate workload-factory gate passed all 25 tests with zero skips. The workflow's unchanged selected-function checks (only the external report path substituted) measured security-critical profile validation at 240/240 lines (100.00%) and catalog-readiness projection at 62/67 (92.54%), both above the required 90%. An initial factory invocation used a synchronous database URL and failed before collection; its state was retained and the correct async-driver invocation used separate new task-owned paths.
- Lychee used the hosted input/exclusion set with cache disabled: 194 total links, 85 unique, 189 successful, 5 excluded, 2 redirects, zero errors or timeouts. Its private report and pytest XML remain outside tracked source. Text-only diff, credential/public-path inspection, and `git diff --check` passed.
- Final read-only preservation audit found all eight named historical roots, the unchanged seven historical synthetic roots, all three predecessor worktrees at their original heads, and the unchanged security-deferral stash. The primary checkout remains clean at its original older main head. No task-owned process candidate remained. Slice-owned validation evidence, the incomplete-attempt database, and temporary state are retained; there was no cleanup campaign. Normal publication and exact-head hosted/connector results are still separate from this local checkpoint.

Measured CI module gates (percent):

| Module | Measured | Required |
| --- | ---: | ---: |
| extensions/contracts | 95.40 | 85 |
| extensions/interfaces | 94.17 | 85 |
| extensions/loader | 100.00 | 85 |
| extensions/runtime | 100.00 | 85 |
| extensions/builtin/task_metrics | 92.59 | 85 |
| extensions/builtin/plan_metrics | 95.00 | 85 |
| extensions/builtin/plan_latency | 87.76 | 80 |
| extensions/builtin/plan_snapshot | 100.00 | 80 |
| extensions/builtin/activity_feed | 100.00 | 85 |
| extensions/observability | 97.73 | 80 |
| observability/diagnostics | 90.16 | 80 |
| observability/health | 95.78 | 85 |
| observability/activity | 94.83 | 80 |
| observability/overview | 100.00 | 85 |
| application/task_service | 79.23 | 75 |
| application/configuration_service | 90.58 | 85 |
| execution_operator/config | 89.04 | 85 |
| execution_operator/lifecycle | 88.27 | 75 |
| execution_operator/models | 90.29 | 90 |
| execution_operator/preflight | 89.47 | 75 |
| execution_operator/processes | 77.53 | 75 |
| execution_operator/runtime | 85.13 | 75 |

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
