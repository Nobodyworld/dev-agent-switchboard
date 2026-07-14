# Implement the pull-based trusted-manifest local worker

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

Primary implementation issue: #113. Parent epic: #111. The execution control plane was completed in #112 and merged by PR #116.

## Purpose / Big Picture

Switchboard now persists approved work orders, workers, execution runs, and active leases, but it still does not perform deterministic work. This change adds the first real local worker.

An operator will run a new outbound-only worker process on a trusted workstation. The worker will advertise bounded capabilities, poll Switchboard for one eligible approved run, resolve the same trusted manifest identity used by the server, create a disposable worker-owned Git worktree at the exact requested SHA, execute only fixed reviewed argv steps with `shell=False`, maintain heartbeats, report bounded structured results, and clean up.

The user-visible proof is a harmless `worker-smoke@1` manifest executed against a temporary local Git repository. The canonical checkout must remain unchanged, the exact SHA must be verified before process launch, and no caller-controlled command text may reach `subprocess`.

This issue does not deliver the full `validate-switchboard@1` evidence workflow. Durable artifacts, retention, evidence fingerprints, and compact evidence APIs remain issue #114.

## Progress

- [x] Phase 1 control-plane contracts merged to `main` in PR #116.
- [x] Canonical worker base established at `765b7167457e523b9edc0b230039ed407060274b`.
- [x] Implementation branch `feat/pull-based-local-worker` created.
- [x] Worker security and repository-ownership decisions locked in issue #113.
- [ ] Inspect the merged execution schemas, API responses, and client conventions in detail.
- [ ] Add trusted executable step definitions while keeping API output metadata-only.
- [ ] Add execution-specific HTTP client methods with bounded retry behavior.
- [ ] Add worker configuration, repository registry, and capability discovery.
- [ ] Add exact-SHA disposable checkout and contained cleanup.
- [ ] Add fixed-argv process execution, output bounding, redaction, and process-tree termination.
- [ ] Add worker and run heartbeat/cancellation coordination.
- [ ] Add `worker-smoke@1` and end-to-end temporary-repository proof.
- [ ] Add focused security, concurrency, timeout, cancellation, and restart tests.
- [ ] Update operator and API documentation.
- [ ] Run complete repository validation.
- [ ] Open a draft PR linked to #113 and record final evidence here.

## Surprises & Discoveries

- Observation: `scripts/local_runner.py` is a task-coordination demonstration and must remain separate from execution work.
  Evidence: It registers an agent, checks out `/api/tasks/checkout`, heartbeats a task, or marks it complete. It has no execution-run, manifest, checkout, process, or cleanup behavior.

- Observation: The merged execution router already supplies worker registration, checkout, run heartbeat, and completion endpoints, and protects the entire execution router with the Phase 1 admin token.
  Evidence: `server/api/routers/execution.py` registers `POST /api/execution/workers`, `POST /api/execution/checkout`, `POST /api/execution/runs/{run_id}/heartbeat`, and `POST /api/execution/runs/{run_id}/complete` under a router-wide `require_admin_token` dependency.

- Observation: `server/execution/registry.py` intentionally stores only safe metadata. The digest currently excludes executable argv because #112 was control-plane only.
  Evidence: The module comments explicitly defer executable behavior, and `TrustedManifest.digest` hashes metadata such as step IDs and timeouts but not argv.

- Observation: `docs/examples/execution/validate-switchboard-v1.yaml` contains illustrative argv, but its header states that it is not executable until #112-#114 are implemented.
  Evidence: The example is documentation, not a trusted runtime loader. Do not make arbitrary YAML files executable merely by placing them in the repository.

## Decision Log

- Decision: Add a new worker entry point rather than changing `scripts/local_runner.py`.
  Rationale: Task coordination and deterministic execution have different trust, lifecycle, and cleanup semantics. Keeping them separate prevents a demo runner from becoming a general execution path.
  Date/Author: 2026-07-14 / ChatGPT connector review

- Decision: Place reusable worker code in a focused package under `client/python/`, with `scripts/local_worker.py` limited to CLI configuration and lifecycle startup.
  Rationale: The worker is an outbound API client, not a server request handler. A focused package makes process, Git, configuration, and transport code testable without importing the CLI.
  Date/Author: 2026-07-14 / ChatGPT connector review

- Decision: Extend the existing trusted Python manifest registry with private immutable executable-step definitions and include them in the manifest digest.
  Rationale: Server and worker must resolve the same reviewed name/version/digest. Keeping definitions in code avoids a new parser dependency and prevents arbitrary repository files from becoming executable. API schemas must continue to omit argv and executable paths.
  Date/Author: 2026-07-14 / ChatGPT connector review

- Decision: Add a minimal `worker-smoke@1` manifest for #113 and leave the full `validate-switchboard@1` runtime profile to #114.
  Rationale: #113 must prove safe execution, cancellation, and cleanup without prematurely implementing complete validation evidence, dependency provisioning, browser execution, or artifact retention.
  Date/Author: 2026-07-14 / ChatGPT connector review

- Decision: Map repository full names to operator-configured canonical local Git paths; never accept filesystem repository paths from work orders.
  Rationale: The server approves logical repository identity. The local worker alone owns the mapping to trusted local resources, preventing remote path selection and traversal.
  Date/Author: 2026-07-14 / ChatGPT connector review

- Decision: Use detached Git worktrees beneath a configured worker root and verify `HEAD` equals the exact work-order SHA before running a step.
  Rationale: Worktrees provide deterministic disposable source trees while preserving the canonical checkout. Git metadata changes needed to create and remove the worktree are allowed; source modification, staging, commits, pushes, rebases, and merges are not.
  Date/Author: 2026-07-14 / ChatGPT connector review

- Decision: Do not claim process-level network isolation in #113.
  Rationale: Cross-platform network sandboxing is not available through the current standard-library design. `worker_restricted` describes an operator-controlled trusted network posture, not a per-process firewall. The worker must reject policies it cannot truthfully satisfy.
  Date/Author: 2026-07-14 / ChatGPT connector review

## Outcomes & Retrospective

Not complete. At completion, record:

- final worker package and entry-point paths;
- exact trusted-manifest representation and digest behavior;
- checkout and cleanup containment guarantees;
- process-tree cancellation implementation by platform;
- test and coverage counts;
- hosted CI run IDs;
- remaining limitations deferred to #114.

## Context and Orientation

The relevant merged control-plane files are:

- `server/execution/registry.py` — trusted manifest metadata and digest.
- `server/execution/schemas.py` — API request/response contracts.
- `server/execution/entities.py` — domain values used by the service.
- `server/execution/enums.py` — work-order, run, worker, network, and write-policy enums.
- `server/execution/service.py` — lifecycle, checkout, heartbeat, completion, and stale-lease logic.
- `server/api/routers/execution.py` — authenticated execution endpoints.
- `client/python/switchboard_client.py` — current synchronous HTTP-client conventions.
- `scripts/local_runner.py` — existing task demo that must remain stable.
- `docs/examples/execution/validate-switchboard-v1.yaml` — non-executable future validation example.
- `docs/architecture/local-execution-broker.md` — accepted pull-based security architecture.
- `.agent/execplans/006_execution_plane_contracts.md` — completed Phase 1A control-plane plan and evidence.

The existing execution API surface needed by the worker is:

- `GET /api/execution/manifests`
- `GET /api/execution/manifests/{name}/{version}`
- `POST /api/execution/workers`
- `POST /api/execution/workers/{worker_id}/heartbeat`
- `POST /api/execution/checkout`
- `GET /api/execution/runs/{run_id}`
- `POST /api/execution/runs/{run_id}/heartbeat`
- `POST /api/execution/runs/{run_id}/complete`

The worker must use the configured Phase 1 admin token without logging it. Non-idempotent operations such as checkout and completion must not be blindly retried after ambiguous failures.

## Plan of Work

### 1. Define trusted executable manifests

Extend `server/execution/registry.py` or a tightly related module with immutable trusted step definitions. A step should contain at least:

- stable step ID and title;
- fixed argv tuple;
- required versus diagnostic-only behavior;
- working-directory relative path;
- fixed environment additions;
- timeout;
- optional capability condition;
- output-summary limit.

The full manifest digest must include the executable, every argv element, fixed environment additions, working directory, timeout, condition, and required/diagnostic behavior.

Keep `CommandManifestOut` and all API responses metadata-only. Add regression tests that API serialization never includes argv, executable paths, or fixed secret-bearing environment values.

Add `worker-smoke@1`. Use only harmless reviewed steps that are portable across supported test environments. Do not rely on shell syntax. A practical smoke may record `python --version` and verify repository identity through a fixed Git argv step.

### 2. Add execution API client methods

Either extend `client/python/switchboard_client.py` with clearly named execution methods or add an execution-specific client adapter that reuses its HTTP/session conventions.

Required operations:

- list/get safe manifest metadata;
- register/refresh worker;
- worker heartbeat;
- checkout;
- get run;
- run heartbeat;
- complete run.

Use bearer authentication. Return typed local dataclasses or carefully validated mappings rather than passing unbounded raw dictionaries throughout the worker.

Retry rules:

- GET and clearly idempotent heartbeat operations may retry bounded transient failures.
- Checkout and completion must not be replayed automatically after an ambiguous network failure.
- Surface HTTP 404/409 on run heartbeat as ownership loss or cancellation, not a generic retry loop.

### 3. Add worker configuration and capability discovery

Create an immutable validated configuration containing:

- server base URL;
- worker ID/display name;
- admin token source;
- polling and heartbeat intervals;
- worker root;
- repository registry mapping full name to canonical local path;
- maximum concurrency;
- network-policy capability;
- output and disk limits;
- inherited environment allowlist;
- redacted key and value patterns.

Secrets should come from environment or a local ignored configuration source, never committed examples with real values.

Capability discovery must be bounded. It may inspect platform information and use fixed safe version probes for Python, Node, Git, Docker, and supported browsers. It must not execute code from a target repository.

### 4. Implement repository resolution and disposable checkout

Resolve the work-order repository full name through the local registry. Canonicalize and validate the configured source repository before use.

Generate a run-owned directory beneath the worker root. Prove containment using resolved paths and reject:

- `..` traversal;
- symlink or junction escape;
- deletion of the worker root itself;
- cleanup of paths not created for the current run.

Use fixed Git argv with `shell=False` to:

- verify the requested object is a commit;
- create a detached worktree at the exact SHA;
- read back `HEAD`;
- remove the worktree during cleanup;
- prune only safe stale metadata when required.

Tests must use temporary local Git repositories and verify the canonical working tree, index, branch, and tracked contents remain unchanged.

### 5. Implement fixed-argv process execution

Create a process runner that accepts only a resolved trusted step object. The public API of this runner must not accept an arbitrary command string.

For every step:

- validate the relative working directory remains inside the disposable checkout;
- build a fresh environment from the explicit allowlist and fixed values;
- open stdout/stderr files beneath the run directory;
- launch with `shell=False`;
- create a platform-appropriate process group/session;
- maintain bounded tail/head summaries while full logs remain local;
- redact configured secrets in summaries;
- enforce step and overall deadlines;
- terminate the process tree on timeout, cancellation, ownership loss, or shutdown;
- record truthful duration and exit code.

Use standard-library process-group controls first. If Windows descendant cleanup cannot be implemented reliably without a dependency, reproduce the limitation, add the narrowest justified dependency, and record it in this plan.

### 6. Coordinate polling, heartbeats, cancellation, and completion

The worker loop should:

1. register capabilities;
2. heartbeat while idle;
3. poll checkout;
4. validate repository, digest, policy, capability, and limits again locally;
5. create the run directory and checkout;
6. heartbeat the run while executing steps;
7. stop immediately on server cancellation or ownership loss;
8. clean up;
9. submit one truthful terminal completion only when the worker still owns the run;
10. return to polling after bounded recovery.

The worker must distinguish:

- no eligible work;
- capability mismatch;
- transient server outage;
- cancelled run;
- ownership conflict;
- manifest mismatch;
- checkout failure;
- process failure;
- timeout;
- cleanup failure.

Interrupted restart behavior must not re-execute an active run without an owned lease. On restart, the worker registers and polls normally; stale lease recovery remains server-controlled.

### 7. Report bounded Phase 1 results

Use the existing completion fields to record bounded structured metadata. Include:

- manifest identity and digest;
- tested repository and exact SHA;
- failing step ID;
- step statuses, durations, and exit codes;
- redacted stdout/stderr summaries;
- relative local-log references;
- environment fingerprint summary;
- checkout verification result;
- cleanup status.

Do not add durable server artifact storage, retention processing, evidence reuse, or full-log API responses.

### 8. Add documentation and tests

Document:

- how to configure and start the worker;
- repository registry format;
- worker-root ownership requirements;
- credential handling;
- supported and unsupported network policy claims;
- manifest trust model;
- cancellation and cleanup behavior;
- Phase 1 limitations and #114 boundary.

Add focused unit and integration tests listed in issue #113. Keep the end-to-end smoke deterministic and local.

## Concrete Steps

Start from the exact branch and base:

```bash
git fetch origin --prune
git switch feat/pull-based-local-worker
git pull --ff-only
git rev-parse HEAD
git rev-parse origin/main
git rev-parse origin/feat/pull-based-local-worker
git status --short
```

At the initial handoff, all three refs must descend from:

```text
765b7167457e523b9edc0b230039ed407060274b
```

The branch already contains this ExecPlan commit, so its `HEAD` will be newer than the base SHA. The worktree must be clean.

Inspect the files listed in Context and Orientation before editing. Update this plan as discoveries change implementation details.

Run focused tests frequently. Before publication, run the complete validation sequence from issue #113 and record every command, exit code, pass/fail/skip count, and relevant environment limitation.

Push only to `feat/pull-based-local-worker`. Open a draft PR targeting `main`. Do not merge it.

## Validation and Acceptance

Acceptance requires all of the following:

1. API callers still cannot provide command text, argv, executable paths, or script bodies.
2. The trusted digest changes when any fixed executable step field changes.
3. API manifest responses do not expose executable details.
4. The worker resolves repository full name only through local trusted configuration.
5. A temporary exact-SHA worktree is created under the worker root and verified before execution.
6. The canonical checkout remains unchanged.
7. Every process uses `shell=False` and trusted fixed argv.
8. Environment inheritance is allowlisted and secret-like values are redacted from summaries.
9. Timeouts, cancellation, and heartbeat ownership loss terminate the full process tree.
10. Cleanup cannot escape the worker root and cleanup failures are surfaced.
11. Two workers cannot execute the same active run.
12. `worker-smoke@1` completes against a temporary repository and reports the exact SHA.
13. Full repository validation passes, including strict browser tests, security, full-history Gitleaks, and coverage gates.
14. PR scope contains no GitHub integration, provider routing, MCP, RPA, target-repository writes, or #114 artifact/evidence system.

## Idempotence and Recovery

- Re-running capability registration is expected and should update the existing worker record.
- Idle heartbeat is repeatable.
- Checkout and completion are not automatically retried after ambiguous transport failures.
- A failed checkout setup must clean only the current run-owned directory.
- Process termination may be called more than once safely.
- Cleanup should be designed as idempotent: missing already-removed worker-owned paths are success, but unexpected external paths are hard failures.
- A crashed worker leaves lease expiry and requeue to the control plane. Restart must not infer ownership from local files alone.
- Keep local run directories for failed cleanup cases when deletion would destroy diagnostic evidence; report that state explicitly.

## Artifacts and Notes

Record here during implementation:

- representative safe manifest digest inputs;
- temporary-repository checkout transcript;
- process-tree cancellation proof on supported platforms;
- redaction and output-bound examples;
- cleanup-containment proof;
- final PR number and head SHA;
- hosted run IDs and exact test counts.

Do not commit real tokens, local repository paths, full environment dumps, generated logs, temporary worktrees, virtual environments, or test databases.

## Interfaces and Dependencies

Expected interfaces, names may vary if the final design remains cohesive:

- `TrustedStep` and executable fields on `TrustedManifest` in `server/execution/registry.py` or a related trusted-only module.
- A safe metadata projection used by `CommandManifestOut`.
- `ExecutionClient` methods for worker registration, checkout, heartbeat, run read, and completion.
- `WorkerConfig` and `RepositoryRegistry` validation.
- `CapabilityDiscovery` returning the existing worker-registration shape.
- `CheckoutManager` or equivalent for exact-SHA worktree creation and cleanup.
- `TrustedProcessRunner` accepting a resolved trusted step, never raw caller argv.
- `WorkerLoop` coordinating polling, heartbeats, cancellation, execution, and completion.
- `scripts/local_worker.py` as the operator entry point.

Prefer the standard library and existing dependencies. Any new dependency requires a reproduced need, security review, lock/requirements update, and documentation in the Decision Log.
