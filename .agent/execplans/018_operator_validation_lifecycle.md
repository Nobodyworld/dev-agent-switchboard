# Orchestrate the trusted local validation lifecycle

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Issue #149 proved that reviewed Switchboard can validate itself through one authoritative seven-step fresh `validate-switchboard@1` run and then complete one distinct same-worker `allow_exact` run with zero repeated deterministic steps. The proof succeeded, but operating it required a long manual sequence: establish isolated roots and toolchains, start the server and worker, create and explicitly approve two work orders, observe lifecycle state, verify local evidence, normalize safe representations, shut down processes, and assemble a sanitized report.

Issue #151 turns that proven process into one supported local operator command. After this slice, an operator can provide an allowlisted canonical checkout, exact SHA, trusted manifest, new runtime root, and explicit approvals, then observe a fail-closed lifecycle:

```text
exact preflight
    -> marker-owned isolated runtime
    -> controlled server and worker startup
    -> explicit fresh approval
    -> terminal fresh evidence verification
    -> optional explicit exact-reuse approval
    -> zero-step reuse verification
    -> controlled shutdown and cleanup verification
    -> bounded machine and human reports
```

The command reduces repetitive orchestration. It does not weaken approval, exact-source, manifest, credential, evidence, containment, or cleanup boundaries. It is not a remote shell, source editor, installer, deployment tool, automatic approval system, new credential model, or operating-system sandbox.

The repository remains:

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

## Authority and Exact Starting State

```text
parent epic: #111
completed predecessor issue: #149
merged predecessor PR: #150
starting main: fbaf2f6170a9f5a27e6573d9d664923cef8f6ae6
active issue: #151
campaign branch: feat/operator-validation-lifecycle
pull request: #152 — open draft
living ExecPlan: .agent/execplans/018_operator_validation_lifecycle.md
```

Issue #151 is the accepted contract. This plan may clarify implementation details but must not expand its scope.

## Observable Completion

A trusted operator can run one repository-supported command in either `fresh-only` or `fresh-then-exact-reuse` mode. The command performs exact read-only preflight, creates a new marker-owned runtime, starts the reviewed server and outbound worker, requires visible explicit approval before each work order, waits for authoritative terminal state, verifies compact and retained evidence, shuts down only proven-owned processes, verifies cleanup, and writes bounded sanitized reports.

The command exits non-zero and preserves the owned runtime whenever any required preflight, startup, execution, completion, evidence, reuse, shutdown, or cleanup assertion fails. It never repairs database state, fabricates success, creates reuse after incomplete fresh proof, or deletes uncertain state.

## Progress

- [x] PR #150 squash-merged as `fbaf2f6170a9f5a27e6573d9d664923cef8f6ae6`.
- [x] Issue #149 closed as completed after merge confirmation.
- [x] Issue #151 created with locked scope and exclusions.
- [x] Canonical branch `feat/operator-validation-lifecycle` created from exact merged main.
- [x] Living ExecPlan 018 created.
- [x] Reconcile and link the existing draft pull request #152.
- [x] Inspect current CLI, worker, server-launch, API-client, schema, evidence, containment, and operations conventions.
- [x] Finalize the supported command name, module placement, typed configuration, and report schemas without creating a competing CLI framework.
- [x] Implement exact preflight and fail-closed safe-state reporting.
- [x] Implement marker-owned runtime creation and foreign/unknown-runtime rejection.
- [x] Implement process-only credential handling and leak-proof diagnostics.
- [x] Implement controlled FastAPI server and outbound-worker startup, health observation, shutdown, and ownership verification.
- [x] Implement explicit fresh approval and `fresh-only` lifecycle observation.
- [x] Implement guarded `fresh-then-exact-reuse` with a second explicit approval only after authoritative fresh success.
- [x] Implement bounded machine-readable and human-readable reports.
- [x] Add unit, contract, process, Windows, failure-boundary, and synthetic fresh/reuse integration tests.
- [x] Preserve all existing manual entry points and update operator documentation.
- [x] Run focused validation, the complete repository matrix, strict browser/security/coverage gates, and one bounded synthetic lifecycle proof.
- [x] Reconcile this ExecPlan and mutable status evidence.
- [x] Reproduce review 5055382298's Linux Mypy failures with Python 3.11 and
  Mypy's Linux platform target; record that native Windows stub selection does
  not reproduce the two Windows-only attribute errors.
- [x] Replace raw origin equality with a closed semantic GitHub HTTPS/SSH
  parser, including the Actions HTTPS form without `.git`.
- [x] Separate the internally derived Switchboard control-plane source from
  the operator-selected target checkout and prove both modes against a target
  fixture with no Switchboard launchers.
- [x] Bind process records, configuration, stop signaling, diagnostics,
  termination, finalization, cleanup, and reports to the complete original
  marker identity through one stable bounded reader.
- [x] Require complete fresh reuse/result identity, hash, fingerprint,
  ownership, containment, artifact, and retention proof in both modes.
- [x] Require exact `first_available`, pinned-worker, zero-quota route proof and
  extend the safe report with identity, route, quota, source, artifact-byte,
  fingerprint, and expiry facts.
- [x] Pass the corrected hosted Mypy reproduction, focused ownership/origin
  matrix, both external-target lifecycle modes individually and together, and
  the affected worker/server/CLI regressions under the required cached pnpm.
- [ ] Commit in logical Conventional Commit units, push normally, and verify exact local/remote parity.
- [ ] Complete exact-head hosted validation and connector review.
- [ ] Keep the pull request draft and unmerged pending separate owner authorization.

## Surprises & Discoveries

- Observation: The accepted issue #149 runtime required four deliberate control-plane actions—create and approve the fresh work order, then create and approve the reuse work order.
  Evidence: ExecPlan 017 records work orders/runs `1/1` and `2/2`, explicit approval for both, and zero-step reuse only after fresh success.

- Observation: Runtime-only verification encountered import-root, path-shape, UTC-representation, and Windows console UTF-8 friction even though product execution and retained evidence were valid.
  Evidence: ExecPlan 017 `Surprises & Discoveries` records each correction and distinguishes it from product or evidence failure.

- Observation: Existing operator entry points are split between `scripts/dev.py`, `scripts.local_worker`, server launch helpers, the browser Validation Broker, and worker/API classes. There is no supported single lifecycle command.
  Evidence: `scripts/dev.py` exposes developer subcommands; `scripts.local_worker` launches one outbound worker from operator JSON; no repository script currently orchestrates the accepted end-to-end lifecycle.

- Observation: Python 3.14 with the pinned Bandit 1.8.6 can emit one manager
  error for every requested file but still return exit code zero.
  Evidence: The retained real lifecycle security log contains manager errors
  for the entire server tree; the command-level and worker result parsers now
  detect that condition and fail closed instead of accepting a false audit.

- Observation: Windows source-checkout execution needs an explicit repository
  import root, and report-safe redaction must happen before byte truncation.
  Evidence: Direct CLI help initially could not import `client`, while a large
  sanitized Bandit diagnostic expanded beyond the report string ceiling after
  pre-sanitization truncation. Both boundaries have regression coverage.

- Observation: The real seven-step run is dominated by the full test step and
  therefore takes about twenty minutes on this host.
  Evidence: The retained successful mechanical run used `1124.719` seconds for
  tests-with-coverage and `1207.82` seconds end to end; exact reuse then executed
  zero deterministic steps.

- Observation: Native Windows Mypy selected Windows `stat` stubs and passed the
  original exact command, while `--platform linux` reproduced the hosted
  `st_file_attributes` and `FILE_ATTRIBUTE_REPARSE_POINT` errors exactly.
  Evidence: Python 3.11 / Mypy 1.18.2 reported those two errors before the
  correction and `Success: no issues found in 199 source files` afterward.

- Observation: The checkout's `.git` HTTPS origin made the original local
  synthetic node pass, while Actions' equally valid non-`.git` form failed at
  the reviewed head with `source_origin_mismatch`.
  Evidence: Blocking review 5055382298 is bound to
  `7db2fb4674ffba4c2f92497871f4cf0931234e7a`; the corrected separate-target
  fixture uses the non-`.git` form and passes fresh-only and exact reuse.

- Observation: A PowerShell `.cmd` shim exposes cached pnpm 10.18.1 to the
  shell but is intentionally rejected by strict child containment as a worker
  executable. An ignored native task-local wrapper was required for the
  Zscripts capability acceptance without changing host-default pnpm 10.24.0.
  Evidence: discovery first returned `pnpm_available: false`, then returned
  `pnpm_version: 10.18.1` and the isolated Zscripts acceptance passed.

## Decision Log

- Decision: Build a local operator lifecycle, not another workload profile or execution backend.
  Rationale: Fresh execution and exact reuse are already proven. The next highest-value gap is repeatable safe operation, not more execution breadth.
  Date/Author: 2026-08-27 / Owner and GitHub coordinator.

- Decision: Keep approval explicit for both fresh and reuse work orders.
  Rationale: Selecting `fresh-then-exact-reuse` expresses desired mode but does not authorize either control-plane mutation. Approval remains a separate deliberate operator action.
  Date/Author: 2026-08-27 / Owner and GitHub coordinator.

- Decision: Preserve failed runtimes instead of automatic repair or deletion.
  Rationale: A failed runtime is diagnostic evidence. Repairing authoritative records or deleting uncertain state would violate the project trust model.
  Date/Author: 2026-08-27 / Owner and GitHub coordinator.

- Decision: Do not introduce scoped worker credentials or OS-backed isolation in this slice.
  Rationale: Those are separate security architecture changes with their own threat models. This slice must preserve the current Phase-1 process-only token and trusted-worker boundary.
  Date/Author: 2026-08-27 / Owner and GitHub coordinator.

- Decision: Prefer a substantial reusable operator package plus a thin existing-convention CLI integration.
  Rationale: Lifecycle logic needs focused unit testing and clear boundaries; placing all behavior directly in `scripts/dev.py` would produce an untestable monolith, while a second independent CLI framework would fragment operator behavior.
  Date/Author: 2026-08-27 / GitHub coordinator, subject to local source inspection.

- Decision: Expose `python scripts/dev.py validation-lifecycle` and
  `python scripts/dev.py inspect-validation-runtime` as the only new command
  surfaces, backed by `client.python.execution_operator`.
  Rationale: `scripts/dev.py` is the reviewed repository command dispatcher.
  Keeping argument parsing there and lifecycle behavior in a focused package
  preserves the existing convention without creating a competing CLI.
  Date/Author: 2026-08-28 / Codex.

- Decision: Use a strict versioned JSON configuration with local paths confined
  to private configuration and runtime objects, while every public exception,
  console summary, and report uses bounded path-free logical identities.
  Rationale: Operators need exact local checkout and runtime roots, but those
  values must never cross into durable diagnostics or publishable evidence.
  Unknown keys, non-loopback hosts, malformed SHAs, unsupported modes or
  routing, unsafe roots, and out-of-range bounds fail before mutation.
  Date/Author: 2026-08-28 / Codex.

- Decision: The normal command creates a previously absent marker-owned runtime
  exactly once and never resumes or repairs it; the inspection command is a
  separate read-only marker/report reader.
  Rationale: Runtime preservation and foreign-state rejection are core trust
  boundaries. A UUID marker written before owned subdirectories and processes
  gives every later mutation a revalidated ownership identity.
  Date/Author: 2026-08-28 / Codex.

- Decision: Launch the reviewed FastAPI application and outbound worker as
  direct owned children, place them in a Windows Job Object or POSIX process
  group, send a bounded graceful termination first, and use containment
  termination only for verified owned children.
  Rationale: Direct process handles plus marker identities avoid PID guessing,
  shell indirection, and broad host cleanup while retaining crash containment.
  Date/Author: 2026-08-28 / Codex.

- Decision: Reuse existing bounded execution APIs and query only the private
  operator-owned SQLite runtime for the final zero-lease assertion; add no
  server endpoint.
  Rationale: Work-order, approval, queue, worker, route, run, and evidence facts
  are already exposed. Lease cardinality is an internal cleanup assertion for
  this disposable runtime and does not justify expanding the public API.
  Date/Author: 2026-08-28 / Codex.

- Decision: Require a distinct exact confirmation for each fresh and reuse
  work order, with separate `--approve-fresh` and `--approve-reuse` flags for
  deliberate non-interactive operation.
  Rationale: Selecting a lifecycle mode is not approval. Reuse authorization is
  not accepted or requested until fresh terminal state and evidence are fully
  verified.
  Date/Author: 2026-08-28 / Codex.

- Decision: Serialize machine JSON and human text from one strict report model,
  enforcing field, collection, string, and total-byte ceilings as failures.
  Rationale: One source of truth prevents format drift; failing closed rather
  than truncating preserves the meaning of security and acceptance facts.
  Date/Author: 2026-08-28 / Codex.

- Decision: Treat any Bandit manager error as an incomplete security audit even
  when Bandit returns zero.
  Rationale: Command success cannot substitute for evidence that requested
  files were actually scanned. The developer gate and retained-evidence parser
  now share this fail-closed interpretation.
  Date/Author: 2026-08-28 / Codex.

- Decision: Resolve GitHub origins into a strict case-folded owner/repository
  identity while preserving configured logical spelling in public reports.
  Rationale: Transport syntax and optional `.git` do not change repository
  identity, but credentials, ports, lookalikes, traversal, and extra path
  segments must remain hard failures without reflecting raw input.
  Date/Author: 2026-08-28 / Codex.

- Decision: Derive the control-plane root only from the loaded operator module
  and validate its fixed internal launchers; never add it to caller
  configuration or import target source into control-plane children.
  Rationale: The selected canonical checkout is a target trust input, not the
  implementation source for Switchboard's server and worker.
  Date/Author: 2026-08-28 / Codex.

- Decision: Use one complete `RuntimeSummary` equality check and stable marker
  reader as the gate for every post-creation mutation and process action.
  Rationale: Syntactically valid replacement markers are foreign state; a held
  process handle does not authorize signaling, termination, finalization, or
  report overwrite after marker identity is lost.
  Date/Author: 2026-08-28 / Codex.

- Decision: Reuse the worker's complete retained-evidence verifier for every
  successful fresh run and admit only the exact pinned zero-quota route.
  Rationale: Fresh-only is a lifecycle choice, not permission to omit result
  identity, cryptographic artifacts, retention, or route/quota proof.
  Date/Author: 2026-08-28 / Codex.

## Outcomes & Retrospective

The supported surfaces are `python scripts/dev.py validation-lifecycle
--config <private-json>` and the read-only `python scripts/dev.py
inspect-validation-runtime <root>`. The lifecycle supports `fresh-only` and
`fresh-then-exact-reuse`. Selecting a mode never approves a work order:
interactive operation requires one exact confirmation per work order, while
non-interactive operation requires the separate `--approve-fresh` and
`--approve-reuse` flags.

The implementation is deliberately split across
`client/python/execution_operator/{config,models,preflight,runtime,processes,lifecycle}.py`
with a package export, a thin `scripts/dev.py` dispatch surface, and the direct
`scripts/operator_server.py` child launcher. Existing server, execution API,
worker, evidence, and process-containment code remains authoritative. The
manual server and `scripts.local_worker` entry points remain compatible; the
worker gained only marker-owned drain/stop signaling required for bounded
operator shutdown.

Strict configuration rejects unknown fields, non-object/oversize files,
malformed or non-lowercase full SHAs and digests, unsupported modes/routing,
non-loopback hosts, unsafe ports, relative/network/device/traversal paths,
existing or linked roots, overlap, unsafe Windows path budgets, and invalid
timeouts or limits. Preflight verifies clean exact source, origin, tree,
manifest, tools, capability, containment, new roots, port, token presence, and
report policy before mutation. The token exists only in process memory and
child environments; configuration, argv, marker, logs, exceptions, reports,
evidence, and captured output have explicit leak regressions.

Marker schema version 1 is atomically written before owned subdirectories and
binds only safe logical identity. Normal operation refuses existing, foreign,
malformed, linked, or ambiguous state. The lifecycle holds direct child
processes under Windows Job Object or POSIX process-group containment, verifies
health and worker registration, drains before owned termination, and requires
zero leases/capacity, stopped children, clean source state, and a released port.
Any post-marker failure preserves the runtime and attempts one bounded failed
report without retrying or repairing authoritative state. Inspection is
read-only.

The real server/worker synthetic matrix passed both modes. Fresh and reuse use
distinct work-order and run IDs on the same worker. Reuse is not created until
fresh terminal state, local evidence, route, source, leases, capacity, and
expiry have been verified. Exact reuse links to the fresh run, preserves the
source expiry, has zero steps and artifacts, refuses fresh fallback, and reports
seven avoided deterministic steps. Failure, cancellation, port, containment,
worker-exit, token-leak, size-bound, and cleanup cases are covered and repeated
without observed task-owned process or port leakage.

A retained real `validate-switchboard@1` mechanical exercise at implementation
head `c16599c398083e9c8d4c89d1c4ce7b58cfd95aae` completed fresh run `1` and
exact-reuse run `2` in runtime `d903cf91-cdc3-4e02-93e3-03ab9ffff6e4`; reuse
executed zero steps and avoided seven. That exercise is not accepted as a
security-clean full validation because Python 3.14/Bandit 1.8.6 skipped the
server files while returning zero. The final implementation fails closed on
that host condition. A separate trusted Python 3.13 Bandit run passed.

Focused implementation validation reached 247 passes with one documented
platform/version skip; the operator coverage suite reached 82% aggregate and
all six configured module thresholds. The pre-final repository suite reached
752 passes and 11 documented skips, strict Playwright reached four passes and
zero skips, and three repeated leakage matrices reached 24/24 passes. The
Python 3.11 correction candidate at
`2c85948ce7bf5eda37bf36da263a9e42d8fa6865` subsequently passed the complete
`scripts/dev.py verify` sequence with 822 passes, 16 explicit platform/runtime
skips, 88% aggregate coverage, all 20 configured module thresholds, strict
Mypy, Ruff, Bandit, and an environment audit with no known vulnerabilities.
The task-owned environment's bootstrap `setuptools` was advanced from 79.0.1
to fixed 84.0.0 after the first audit identified PYSEC-2026-3447; no repository
dependency or host-default tool was changed. Final exact-head validation and
hosted checks are recorded in the delivery report, because changing this living
document after those gates would invalidate their exact-head binding.

The lifecycle removes manual runtime construction, launch sequencing, polling,
evidence reconciliation, shutdown, cleanup verification, and report assembly.
It deliberately retains target preparation, exact configuration, token
provisioning, and separate human approval for every work order.

The review correction makes that lifecycle portable and multi-repository. The
preflight accepts only semantically equivalent GitHub origins; Switchboard
children launch from an internally derived, reparse-free control-plane root;
the selected canonical checkout remains only the worker target. Every runtime
write and process action is bound to the original marker identity. Every fresh
success requires the same complete retained-evidence identity/hash and
cryptographic artifact path used for reuse. Report schema 2 carries the exact
verified source, identity hash, `first_available` route, pinned worker,
zero-quota state, eligible count, artifact total, fingerprint, expiry, and
cleanup facts without private paths or data.

The corrected focused operator module passed 83 tests with four explicit
capability/gated skips. Both modes passed individually and together against a
separate non-`.git` target fixture that lacks both control-plane launchers. The
two-mode process/port/cleanup selection then passed three consecutive repeats.
requested affected regression set passed after binding the Zscripts capability
case to cached pnpm 10.18.1; the host-default pnpm 10.24.0 was not changed.
The Python 3.11 correction candidate passed the complete repository verify
sequence with 822 passes, 16 explicit platform/runtime skips, 88% aggregate
coverage, all 20 configured thresholds, and clean Ruff, Mypy, Bandit, and
environment-audit results. Strict Playwright, link/secrets/workflow hygiene,
the standalone no-coverage pytest count, and final push parity are rebound to
the final documentation head and recorded in the delivery report.

PR #152 remains
draft and unmerged pending exact-head hosted validation, connector review, and
a separate owner decision.

## Context and Orientation

Switchboard separates the control server from deterministic execution. A trusted outbound worker polls for approved work orders, creates a disposable exact-SHA worktree, executes only reviewed fixed argv from an immutable manifest, retains full logs locally, sends compact redacted evidence to the server, and may reuse evidence only after same-worker local verification.

Key current surfaces:

```text
scripts/dev.py
    Existing repository developer CLI and validation commands.

scripts/local_worker.py
    Thin module entry point that loads operator-owned WorkerConfig and runs the
    outbound LocalWorker. The token comes only from SWITCHBOARD_ADMIN_TOKEN.

scripts/run_uvicorn.py
    Existing server launcher helper and process-start convention.

client/python/execution_worker/config.py
    Strict worker configuration, root, capability, timeout, evidence, and
    inherited-environment contracts.

client/python/execution_worker/client.py
    Bounded authenticated worker HTTP transport and safe error handling.

client/python/execution_worker/worker.py
    Polling, exact-SHA execution, completion, cleanup, and reuse behavior.

client/python/execution_worker/containment.py
    Platform process containment and ownership-sensitive cleanup helpers.

client/python/execution_worker/evidence.py
    Retained local evidence ownership, hashing, retention, and reuse verification.

server/execution/
    Work-order, run, routing, evidence, manifest, and lifecycle contracts.

server/api/routers/execution.py
    Privileged work-order creation, approval, queueing, observation, evidence,
    route, worker, and lifecycle API endpoints.

web/static/validation_broker.js
    Existing browser operator workflow and API usage patterns.

docs/operations/local-worker.md
    Current trusted-worker setup, token, mapping, evidence, and recovery guidance.

.agent/execplans/017_reviewed_main_fresh_reuse_acceptance.md
    Authoritative accepted fresh/reuse evidence and measured operator friction.
```

The likely implementation shape, to confirm locally, is:

```text
client/python/execution_operator/
    __init__.py
    config.py
    models.py
    preflight.py
    runtime.py
    processes.py
    api.py
    lifecycle.py
    reporting.py
    cli.py

scripts/dev.py
    Add a thin `validation-lifecycle` subcommand that delegates to the package.

client/python/tests/
    Focused operator lifecycle tests and synthetic integration coverage.

docs/operations/operator-validation-lifecycle.md
    Supported usage, approval, failure, evidence, and cleanup guidance.
```

Do not preserve this exact file split when repository inspection proves a smaller or more coherent arrangement, but preserve the module boundaries: typed configuration, preflight, owned runtime, process lifecycle, API/lifecycle state machine, reporting, and CLI integration.

## Plan of Work

### 1. Inspect and lock the existing interfaces

Read the current issue, plan, project rules, worker operations guide, CLI parsers, server launcher, worker configuration/client/worker classes, execution API router, schemas, models, evidence/reuse code, process containment, and Validation Broker request flow.

Produce a short internal interface map before editing:

- exact API operations needed to create, approve, queue, inspect, and cancel work;
- exact work-order, run, evidence, route, worker, lease, capacity, and quota fields available;
- existing safe HTTP transport and error types that can be reused or extracted;
- server startup and shutdown contracts;
- worker startup, drain, and shutdown contracts;
- Windows process-tree ownership primitives;
- current manifest lookup and capability discovery functions;
- text/path/URI sanitization utilities;
- report-safe schema conventions.

Do not duplicate an existing client or policy merely because it is currently in a worker-oriented module. Extract a shared helper only when both old and new callers remain covered and compatible.

### 2. Define typed operator configuration and reports

Create strict typed models for the lifecycle command. Required logical inputs should include:

- canonical repository full name;
- canonical checkout path, local-only and never reportable;
- exact full target SHA;
- trusted manifest name and optional expected version/digest guard;
- lifecycle mode: `fresh-only` or `fresh-then-exact-reuse`;
- new runtime root, local-only;
- worker ID and display name;
- loopback host/port selection policy;
- timeout and polling ceilings constrained by manifest/worker contracts;
- routing policy limited to currently accepted local routing;
- report destination, local-only;
- interactive/non-interactive approval policy that remains explicit.

Configuration must reject unknown fields, relative or unsafe paths, root overlap, path traversal, reparse/symlink ambiguity, invalid SHAs, unsupported modes, unsafe hosts, out-of-range ports, and values exceeding existing server/worker bounds.

Define a versioned machine report schema with strict count, depth, string, list, and byte ceilings. Define a concise human renderer from the same safe model. Local-only inputs must be represented by stable logical labels or booleans, not paths.

### 3. Implement exact preflight

Preflight must be read-only and complete before runtime creation or process launch.

Verify:

1. current repository identity and clean canonical Git state;
2. exact target object exists locally and can be detached without fetching;
3. tracked tree identity and before-state snapshot;
4. manifest name/version/digest and fixed requirements;
5. required Python, Git, Node, and pnpm identities using fixed argv, `shell=False`, bounded output, and timeouts;
6. selected worker capability compatibility;
7. safe distinct runtime/evidence/worker/storage/report/TEMP/TMP roots;
8. no requested root exists unless read-only inspection mode is explicitly selected;
9. selected loopback port is available without binding a public interface;
10. Phase-1 token exists in process environment but is never read into serializable configuration or output;
11. report models and redaction policy are initialized before any diagnostic can be emitted.

Return a bounded safe preflight report. Fail before mutation on any mismatch.

### 4. Implement marker-owned runtime creation

Create the runtime root only after preflight passes. Write an ownership marker atomically before database, storage, worker, evidence, report, TEMP/TMP, or process state.

The marker should bind at minimum:

- schema version;
- random runtime identity;
- logical repository full name;
- exact target SHA;
- manifest identity;
- lifecycle mode;
- creation timestamp;
- non-secret logical operator command identity.

Do not include token, user name, machine name, absolute paths, argv, or environment values in any repository-safe representation.

On restart, normal execution must refuse an existing runtime. A separate read-only inspection path may summarize a valid marker-owned runtime but must not resume, migrate, repair, clean, or delete it.

### 5. Implement process and port ownership

Use the existing server app and worker, not test doubles, for the supported command. Use test doubles only in unit tests.

Start processes with direct fixed argv and a minimal allowlisted environment. The token must be injected through the child process environment only. Server database/storage configuration and worker roots are runtime-owned and must not leak into target commands.

Record process identity in private runtime state and bind it to the ownership marker. On Windows, reuse or extend existing Job Object/process-containment behavior rather than relying only on parent PID termination. On POSIX, use process groups/session ownership consistent with current helpers.

Verify server health before worker launch, worker registration before work-order creation, and port ownership before accepting requests. During shutdown, request graceful drain first, then use bounded owned-process termination. Never terminate a PID that cannot be revalidated as owned.

### 6. Implement explicit work-order approvals and state machine

Create an operator-side API layer using existing schemas and safe HTTP/error behavior. It must expose only the fixed operations needed by the lifecycle state machine.

The lifecycle phases should be explicit and persistable in the private report:

```text
preflight_passed
runtime_created
server_healthy
worker_online
fresh_created
fresh_approval_required
fresh_approved
fresh_queued
fresh_running
fresh_succeeded
fresh_verified
reuse_approval_required
reuse_created
reuse_approved
reuse_queued
reuse_succeeded
reuse_verified
shutdown_started
cleanup_verified
completed
```

Failure transitions must record one stable bounded reason and stop further mutations.

Interactive mode must display a safe summary and require a typed confirmation containing a non-secret logical identity. Non-interactive mode may require an explicit approval flag for each work order, but the final report must show that the flag was supplied. Selecting the lifecycle mode alone is never approval.

For `fresh-only`, stop after fresh verification and cleanup. For `fresh-then-exact-reuse`, do not create the reuse work order until fresh terminal and evidence verification pass.

### 7. Verify fresh evidence and cleanup

After authoritative fresh success, verify against server projections and retained local evidence:

- distinct request/work-order/run/worker identities;
- exact repository, SHA, manifest name/version/digest;
- explicit approval and route provenance;
- expected required step identities and statuses;
- terminal succeeded run and work order;
- evidence fingerprint and result/reuse identity;
- artifact identities, count, total bytes, regular-file status, containment, sizes, and SHA-256;
- retention expiry;
- canonical checkout HEAD, branch, tree, staged, unstaged, and untracked state unchanged;
- disposable worktree absent;
- lease count zero;
- worker active capacity zero;
- quota state correct;
- no target process remains.

Any mismatch preserves runtime and blocks reuse.

### 8. Verify exact reuse

For `fresh-then-exact-reuse`, create a second distinct work order only after fresh verification and a second explicit approval.

Verify:

- second work-order and run IDs differ;
- exact fresh source run selected;
- same worker selected;
- ownership marker, local result identity, evidence fingerprint, and every artifact verification succeeded;
- reuse run contains zero deterministic steps and zero new artifacts;
- no fresh fallback occurred;
- exact source-run linkage;
- source evidence expiry unchanged;
- avoided deterministic execution count exact;
- final lease, capacity, quota, process, port, and worktree state clean.

Do not translate avoided count into financial or provider claims.

### 9. Implement bounded sanitized reporting

Write one versioned JSON report and one human summary from a common strict safe model.

Permitted data includes:

- logical repository and manifest identities;
- full commit SHA and immutable digest/hash values;
- stable runtime ID, work-order/run/worker IDs;
- safe route and approval states;
- step names/statuses/durations without commands or logs;
- artifact relative identities, sizes, and SHA-256;
- evidence/reuse fingerprints and expiry;
- cleanup booleans/counts;
- stable reason codes and bounded safe messages;
- operator-action count and non-sensitive friction categories.

Prohibited data includes:

- token or credential values;
- absolute local paths;
- machine/user identity;
- raw environment, argv, request, response, or database content;
- full stdout/stderr or artifact bytes;
- arbitrary exception text;
- private network details.

Run every report through the existing recursive server-safe text/path/URI policy or a shared equivalent before writing. Enforce serialized byte ceilings without slicing JSON text.

### 10. Preserve failure evidence and support read-only inspection

Every failure must preserve the owned runtime. The command may write/update only its bounded private lifecycle report and process markers. It must not repair server records, expire leases manually, remove capacity rows, delete evidence, or reinterpret a partial run.

Provide a read-only `inspect` mode only when it can validate the runtime ownership marker and safely summarize state without starting the server or worker. Do not add resume or cleanup commands in this issue.

### 11. Test in layers

Add focused tests for:

- strict configuration and unknown-field rejection;
- Git identity, dirty-state, missing-object, manifest, tool, root-overlap, reparse, and occupied-port preflight;
- atomic ownership-marker creation and existing/foreign runtime refusal;
- token absence from configuration, argv, logs, diagnostics, reports, and captured exceptions;
- safe process start/health/drain/termination and PID ownership validation;
- Windows Job Object/process tree, UTF-8 console, path, and port-release behavior;
- lifecycle state-machine transitions and no mutation after failure;
- separate explicit fresh and reuse approvals;
- no reuse creation after fresh failure or incomplete evidence;
- fresh-only synthetic integration;
- fresh-then-exact-reuse synthetic integration with distinct records and zero steps;
- report schema bounds, deterministic rendering, and prohibited-value rejection;
- read-only inspection and refusal to resume/repair/clean;
- compatibility of `scripts.local_worker`, server launch, worker config, and existing APIs.

The synthetic integration should use a fast trusted manifest or bounded fixture and the real server/worker/API path. It must not require a full 15-minute `validate-switchboard@1` run in routine tests.

### 12. Document and validate

Add an operations guide with:

- prerequisites and trust boundary;
- exact command examples using placeholders, never real local paths or tokens;
- configuration and mode definitions;
- explicit approval behavior;
- report fields and privacy;
- failure preservation and inspection;
- manual interface compatibility;
- statement that read-only policy is not OS isolation;
- exclusions and developer-preview boundary.

Link it from existing operations and documentation indexes.

Run focused tests, repeated process/port tests, one synthetic fresh/reuse proof, full pytest, coverage and configured thresholds, strict Playwright, formatting, lint, Mypy, Bandit, pip-audit, Gitleaks, detect-secrets, link validation, YAML/TOML, Node syntax, action-pin, TODO, binary/generated-file, credential, and public-path checks.

## Concrete Steps

1. Start read-only from exact branch/base and inspect all local and remote state.
2. Read issue #151, this plan, `PROJECT_RULESET.md`, `.agent/PLANS.md`, ExecPlan 017, worker operations, relevant scripts, worker/client/evidence/containment modules, execution schemas/router, and Validation Broker flow.
3. Record the final interface map and file plan in `Decision Log` before implementation.
4. Implement typed configuration/report models and focused tests first.
5. Implement preflight and runtime ownership with failure tests.
6. Implement process lifecycle and token boundary with Windows/POSIX tests.
7. Implement operator API/state machine and explicit approval behavior.
8. Implement fresh verification, then guarded exact-reuse verification.
9. Implement reporting and read-only inspection.
10. Add the thin supported CLI integration and operations documentation.
11. Run focused tests until stable, then repeated process tests and synthetic integration.
12. Run the complete repository matrix.
13. Update this plan and `docs/reports/status.md` with exact evidence.
14. Stage only reviewed paths, commit in logical units, push normally, verify parity, and stop for connector review.

Expected supported command shape, subject to final source inspection:

```powershell
python scripts/dev.py validation-lifecycle run \
  --config <operator-owned-config.json> \
  --mode fresh-only

python scripts/dev.py validation-lifecycle run \
  --config <operator-owned-config.json> \
  --mode fresh-then-exact-reuse

python scripts/dev.py validation-lifecycle inspect \
  --runtime-root <existing-owned-runtime>
```

The implementation may use a different argparse nesting that fits `scripts/dev.py`, but must provide equivalent clear commands without adding a separate CLI framework.

## Validation and Acceptance

The slice is accepted only when all of the following are proven:

1. The supported command performs complete read-only preflight before mutation.
2. A new marker-owned runtime is created atomically and unknown/existing runtimes are refused.
3. Server and worker processes are started and stopped with proven ownership.
4. The Phase-1 token remains process-only and is absent from every serializable or logged surface.
5. Fresh and reuse approvals are separate explicit actions.
6. `fresh-only` completes and verifies authoritative evidence and cleanup.
7. `fresh-then-exact-reuse` creates a distinct source and reused run, verifies same-worker evidence, executes zero repeated steps, performs no fresh fallback, and preserves source expiry.
8. Any failure prevents unsafe later mutations and preserves the owned runtime.
9. Machine and human reports are bounded, deterministic, sanitized, and path/secret-free.
10. Existing manual server/worker interfaces and execution behavior remain compatible.
11. Focused tests, one synthetic integration, full local validation, exact-head hosted checks, and connector review pass.
12. The PR remains draft and unmerged pending owner authorization.

## Idempotence and Recovery

- Preflight is read-only and repeatable.
- Runtime creation is one-shot: a requested existing root causes refusal, not reuse.
- Ownership markers are written atomically and validated before any mutation or cleanup.
- Work-order creation is never automatically repeated after an ambiguous response.
- Approval is explicit and recorded; selecting a mode is not approval.
- Reuse is never created until fresh proof is complete.
- Failed runtimes are preserved. Normal command execution does not resume, repair, or clean them.
- Read-only inspection never starts processes or mutates the runtime.
- Process cleanup acts only on revalidated marker-owned identities.
- Unknown PIDs, ports, paths, records, or evidence are retained and reported.
- Never use reset, clean, stash, rebase, amend, force-push, broad deletion, or database editing as recovery.

## Artifacts and Notes

Repository artifacts should contain only source, tests, operations documentation, and sanitized evidence summaries.

Local-only artifacts may include:

- operator configuration containing local roots but no token;
- runtime ownership marker;
- private process markers;
- SQLite database and server storage;
- retained local logs and artifact bytes;
- bounded local JSON and human reports;
- test environments and generated reports.

Do not commit or publish local configuration, runtime roots, databases, logs, artifact bytes, tokens, machine identity, absolute paths, environment dumps, or raw process output.

## Interfaces and Dependencies

Preserve and reuse the current reviewed interfaces for:

- `scripts.dev.build_parser` and its subcommand convention;
- `scripts.local_worker` and `WorkerConfig`;
- server application startup and health endpoints;
- `ExecutionClient` safe HTTP behavior or a narrowly extracted shared transport;
- work-order creation, approval, queueing, routing, run, evidence, and worker APIs;
- exact-SHA and manifest/profile registries;
- `LocalWorker` polling and shutdown;
- process containment and ownership verification;
- evidence ownership, retention, artifact hashing, and exact reuse;
- recursive safe text/path/URI policy;
- `first_available` routing and current quota semantics.

New interfaces should be explicit and versioned. Candidate names, subject to local inspection:

```python
class OperatorLifecycleConfig: ...


class OperatorRuntimeMarker: ...


class OperatorLifecycleReport: ...


class OperatorLifecycleFailure: ...


class OperatorApiClient: ...


class OperatorLifecycle: ...


def run_validation_lifecycle(
    config: OperatorLifecycleConfig,
) -> OperatorLifecycleReport: ...


def inspect_validation_runtime(root: Path) -> OperatorLifecycleReport: ...
```

Do not add new server endpoints unless existing bounded APIs cannot establish a required acceptance fact. Any unavoidable API addition must be additive, typed, bounded, omit local/private data, and have separate focused server tests.
