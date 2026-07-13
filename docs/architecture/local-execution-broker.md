# Local Execution Broker Architecture

**Status:** Accepted for Phase 1 implementation

**Parent epic:** [#111](https://github.com/Nobodyworld/dev-agent-switchboard/issues/111)

**Initial implementation issues:** [#112](https://github.com/Nobodyworld/dev-agent-switchboard/issues/112), [#113](https://github.com/Nobodyworld/dev-agent-switchboard/issues/113), and [#114](https://github.com/Nobodyworld/dev-agent-switchboard/issues/114)

## Purpose

Switchboard currently coordinates high-level work through tasks, dependencies,
leases, heartbeats, and agent APIs. The next product stage adds a distinct
execution plane so deterministic validation can run on approved local workers
before a paid coding agent is used.

This document describes the staged target across #112--#114. The #112 release
is deliberately narrower: it persists and validates control-plane contracts
only. It does not validate a checkout, execute a command, collect artifacts,
or return execution evidence. Those worker and evidence behaviors are deferred
to #113 and #114. The resulting system is not a general remote shell,
autonomous coding system, provider router, or desktop RPA platform.

## Accepted Product Decisions

### Separate control plane and worker

Switchboard remains the control plane. A separate local worker registers its
capabilities and pulls eligible work through the Switchboard API.

The worker initiates every connection. It does not expose an inbound control
port on the workstation. A hosted relay or secure MCP tunnel may be added later
without changing the pull-based worker contract.

### Keep GitHub canonical

GitHub remains the source of truth for repositories, issues, pull requests,
branches, and reviewed code changes. A work order identifies a repository and
an exact 40-character commit SHA.

Phase 1 does not permit the worker to commit, push, rebase, merge, or modify the
canonical checkout. A connector or later GitHub adapter may resolve a pull
request to an exact SHA before creating the work order.

### Separate tasks from execution

Existing `Task` records remain human and agent coordination items in the
dependency graph. They answer what work is ready and who owns it.

A `WorkOrder` is a separately persisted request to execute one approved
validation profile. It answers what repository state must be validated, under
which policy, by which kind of worker, and what evidence must be produced.

An `ExecutionRun` records one attempt to execute a work order. Existing task
leases must not be reused as execution-run leases because the lifecycle,
security, retry, and evidence requirements differ.

### Deny by default

A work order is executable only when all of the following are true:

1. The repository is allowlisted.
2. The commit identity is an exact SHA.
3. The manifest name and version exist in the trusted registry.
4. The work order is approved under its policy.
5. An eligible worker declares every required capability.
6. The work order does not request repository write access.
7. The worker can enforce the requested timeout, storage, network, and artifact
   policies.

A mismatch is a rejection, not an instruction for the worker to improvise.

### Execute approved manifests only

Remote agents and work orders cannot submit arbitrary command strings. A work
order references an immutable manifest identity such as
`validate-switchboard@1`.

A manifest is stored in the trusted Switchboard repository and contains fixed
argument vectors. Implementations must use `shell=False` or the
platform-equivalent direct process API.

Template substitution is limited to an explicitly documented set of
Switchboard-owned values such as the disposable worktree path and run artifact
directory. Manifest changes create a new version or digest, and evidence records
the exact digest used.

### Keep target repositories read-only

The worker may create and destroy worker-owned resources:

- disposable clones or Git worktrees;
- virtual environments and package caches;
- containers and networks;
- logs, reports, screenshots, and other declared artifacts.

The worker may not:

- edit the canonical checkout;
- commit or stage source changes;
- push branches or tags;
- rebase, merge, or resolve conflicts;
- open or update pull requests;
- run a general coding agent.

Any future write-capable workflow requires a separate product decision and an
explicit approval model.

### Require explicit approval initially

Read-only validation work orders still require explicit approval in Phase 1.
Automatic approval may later be permitted for a reviewed repository and
manifest pair.

The following always require a separate approval tier and are not part of Phase
1:

- repository writes;
- secrets beyond a worker bootstrap token;
- unrestricted external network access;
- desktop control;
- administrator elevation;
- destructive operations outside worker-owned paths.

### Future artifact retention and evidence redaction (#114)

Issue #112 persists only bounded artifact/evidence metadata placeholders; it
does not store artifacts, logs, hashes, or retention records. In #114,
artifacts will be stored beneath a configured Switchboard storage root in a
run-owned directory, with configurable retention and metadata retained after
artifact expiry.

That later evidence implementation will return bounded summaries and metadata
rather than full logs, and will use an explicit environment allowlist plus
secret/pattern redaction before any result leaves a worker.

### Defer provider routing

Phase 1 records a cost ceiling and preferred-executor metadata but routes only
to deterministic local workers. Provider budgets, remaining rate limits, and
cheapest-capable paid-agent routing are Phase 3 concerns.

The immediate rule is simpler: deterministic validation must not invoke a paid
coding agent.

## Execution-Plane Domain

### WorkOrder

A work order includes at least:

- schema version;
- repository full name;
- exact commit SHA;
- manifest name, version, and resolved digest;
- required worker capabilities;
- permitted paths and forbidden-scope notes;
- expected artifact kinds;
- approval policy and status;
- timeout and resource ceilings;
- requested network and repository-write policies;
- preferred executor and cost-ceiling metadata;
- lifecycle timestamps and terminal reason.

Suggested lifecycle:

```text
pending_approval
    -> approved
    -> queued
    -> assigned
    -> running
    -> succeeded | failed | timed_out | cancelled

pending_approval -> rejected
approved | queued -> cancelled | expired
```

Terminal work orders are immutable except for operator annotations that do not
alter execution identity.

### Worker

A worker includes at least:

- stable worker ID and display name;
- operating system and architecture;
- available Python and Node versions;
- Docker availability;
- supported browsers;
- optional GPU, Unity, and desktop-automation flags;
- maximum concurrency;
- supported network-policy level;
- repository-write capability;
- current status and last heartbeat.

Phase 1 workers must declare repository-write capability as false.

Suggested states:

```text
online | busy | draining | offline
```

### CommandManifest

A command manifest includes at least:

- schema version;
- immutable name and version;
- description;
- fixed-step contract metadata (no argv in Phase 1A);
- required capabilities;
- allowed environment keys and fixed values;
- network and repository-write policy;
- per-step and overall timeouts;
- output limits;
- artifact declarations;
- failure behavior;
- manifest digest.

Issue #112 records the safe metadata and digest only. Fixed argument-vector
steps and their execution semantics are deferred to #113.

### ExecutionRun

An execution run includes at least:

- work-order and worker references;
- attempt number;
- lease and heartbeat metadata;
- queued, assigned, started, and finished timestamps;
- terminal status and bounded result/cleanup metadata;
- artifact/evidence metadata placeholders only (no stored files or
  fingerprints in #112).

Only one active execution run may exist for a work order at a time.

## Future Worker Flow (#113/#114)

The first three control-plane steps are implemented by #112. Steps 4--10 are
the intended later worker/evidence flow and do not describe current #112
behavior.

```text
1. Worker registers capabilities.
2. Worker polls for eligible approved work.
3. Switchboard atomically assigns one work order and creates an execution run.
4. Worker validates repository, SHA, manifest, capability, approval, and policy.
5. Worker creates an isolated worker-owned checkout at the exact SHA.
6. Worker executes fixed argument-vector steps and sends heartbeats.
7. Worker captures bounded progress, full local logs, artifacts, and hashes.
8. Worker reports success, failure, timeout, or cancellation.
9. Worker removes worker-owned transient resources.
10. Switchboard exposes compact evidence for connector or operator review.
```

If a worker loses its lease, it must stop execution and clean up. It may not
continue and later submit stale results as authoritative evidence.

## Security Boundaries

For #112, the active boundaries are the protected control API, trusted manifest
identity, exact SHA policy metadata, read-only repository policy, and absence
of command execution. Filesystem, process-execution, and evidence controls
listed below are requirements for the later #113/#114 worker implementation.

The implementation must protect these boundaries:

- **Control API:** privileged creation, approval, cancellation, and manifest
  administration use admin-token protection or a narrower documented
  equivalent.
- **Worker identity:** worker checkout, heartbeat, and completion use a scoped
  credential. Temporary Phase 1 reuse of the admin token must be documented as
  a limitation.
- **Filesystem:** worktrees, environments, logs, and artifacts remain under
  configured worker-owned roots after path resolution and symlink checks.
- **Process execution:** direct argument-vector execution, timeouts, output
  limits, cancellation, and process-tree termination.
- **Repository:** exact SHA, allowlisted origin, read-only policy, and disposable
  checkout.
- **Manifest:** trusted registry, immutable identity, digest, and no remote
  command injection.
- **Evidence:** bounded summaries, artifact hashes, redaction, retention, and
  truthful cleanup status.

## Future First End-to-End Target (#113/#114)

```text
Connector or operator identifies a pull-request head SHA
    -> creates a read-only work order
    -> approves a trusted validation manifest
    -> eligible local worker pulls the run
    -> worker validates the exact SHA in an isolated checkout
    -> Switchboard returns compact evidence and artifact references
    -> connector reviews the evidence
```

The first target does not automatically post GitHub comments or check runs. It
exposes evidence in a form that the existing connector can review. GitHub event
ingestion and posting are Phase 2.

## Implementation Phases

### Phase 1A — Contracts and lifecycle

Tracked by #112:

- work-order, worker, manifest, and execution-run models;
- persistence and migration behavior;
- validated state transitions;
- capability-aware atomic checkout;
- execution API;
- no command execution.

#### Phase 1A implementation boundary

Issue #112 persists the control-plane records in separate execution tables:
command manifests, work orders, workers, execution runs, and active execution
leases. Startup continues to use additive `Base.metadata.create_all()` behavior;
there is no migration-framework rollout in this phase.

The trusted manifest registry is version-controlled in
`server/execution/registry.py`. It stores immutable identity, digest, and safe
contract metadata only. The illustrative YAML in
`docs/examples/execution/validate-switchboard-v1.yaml` remains a later-stage,
non-executable reference: Phase 1A does not expose its argv data through an API
or turn request input into executable steps.

Checkout reserves a worker capacity slot with a guarded database update, then
conditionally changes a queued work order to assigned and creates a run plus a
unique active lease in the same transaction. The unique
`execution_leases.work_order_id` association is the database-enforced
one-active-run invariant. Releasing the active lease on terminal completion or
stale expiry preserves historical `ExecutionRun` rows. Stale leases mark the
old run timed out and requeue the nonterminal work order for a later attempt.
Lease renewal, completion, cancellation, and expiry all use guarded DML against
the exact active lease so a stale expiry cannot override a renewed heartbeat
and only one actor can release capacity.

For the temporary Phase 1 credential model, worker registration, checkout,
heartbeats, and completion reuse the configured admin token alongside the
privileged operator routes. This is explicitly not a worker identity system and
must be replaced by a scoped worker credential before a worker can execute
anything. Repository-write capability and work-order policy remain false, and
no #112 code launches a process, writes a target repository, or collects
artifacts.

### Phase 1B — Safe pull worker

Tracked by #113:

- worker configuration and capability discovery;
- isolated worktree lifecycle;
- approved direct argument-vector execution;
- heartbeat, cancellation, timeout, output bounding, and cleanup;
- harmless end-to-end worker smoke.

### Phase 1C — Exact-SHA evidence

Tracked by #114:

- first trusted validation manifest;
- artifact and evidence records;
- environment and manifest fingerprints;
- compact evidence API;
- retention and redaction;
- exact-SHA end-to-end validation.

### Later phases

- evidence reuse and known-baseline failures;
- GitHub event and result adapters;
- GitHub Actions versus local-worker routing;
- MCP tools and secure outbound tunnel integration;
- provider budget and rate-limit routing;
- browser worker;
- restricted desktop or RPA worker on a dedicated machine or VM.

## Non-Goals

Phase 1 does not provide:

- arbitrary remote shell access;
- autonomous code changes;
- provider dispatch;
- MCP connectivity;
- GitHub writes;
- browser visual automation;
- desktop RPA;
- administrator elevation;
- a hosted multi-tenant execution service.

## Acceptance Summary

Issue #112 is successful when an approved work order for an allowlisted
repository and exact SHA can be atomically assigned to one eligible worker
through a trusted read-only manifest identity, without modifying the canonical
checkout or consuming paid coding-agent credits. Worker execution and truthful
structured evidence are explicitly deferred to #113 and #114.
