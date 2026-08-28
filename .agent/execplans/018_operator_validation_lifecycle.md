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
pull request: pending connector creation
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
- [ ] Create and link the draft pull request.
- [ ] Inspect current CLI, worker, server-launch, API-client, schema, evidence, containment, and operations conventions.
- [ ] Finalize the supported command name, module placement, typed configuration, and report schemas without creating a competing CLI framework.
- [ ] Implement exact preflight and fail-closed safe-state reporting.
- [ ] Implement marker-owned runtime creation and foreign/unknown-runtime rejection.
- [ ] Implement process-only credential handling and leak-proof diagnostics.
- [ ] Implement controlled FastAPI server and outbound-worker startup, health observation, shutdown, and ownership verification.
- [ ] Implement explicit fresh approval and `fresh-only` lifecycle observation.
- [ ] Implement guarded `fresh-then-exact-reuse` with a second explicit approval only after authoritative fresh success.
- [ ] Implement bounded machine-readable and human-readable reports.
- [ ] Add unit, contract, process, Windows, failure-boundary, and synthetic fresh/reuse integration tests.
- [ ] Preserve all existing manual entry points and update operator documentation.
- [ ] Run focused validation, the complete repository matrix, strict browser/security/coverage gates, and one bounded synthetic lifecycle proof.
- [ ] Reconcile this ExecPlan and mutable status evidence.
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

## Outcomes & Retrospective

Pending implementation.

The final retrospective must record:

- the exact supported command and modes;
- configuration and approval UX;
- preflight, runtime ownership, process, credential, report, evidence, and cleanup contracts;
- synthetic fresh/reuse identities and zero-step proof;
- failure-preservation behavior;
- compatibility with manual server and worker entry points;
- operator actions eliminated versus those deliberately retained;
- validation results and environment limitations;
- final branch and hosted-review state.

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

def run_validation_lifecycle(config: OperatorLifecycleConfig) -> OperatorLifecycleReport: ...
def inspect_validation_runtime(root: Path) -> OperatorLifecycleReport: ...
```

Do not add new server endpoints unless existing bounded APIs cannot establish a required acceptance fact. Any unavoidable API addition must be additive, typed, bounded, omit local/private data, and have separate focused server tests.
