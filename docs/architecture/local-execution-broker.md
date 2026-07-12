# Local Execution Broker Architecture

**Status:** Accepted for Phase 1 implementation

**Parent epic:** [#111](https://github.com/Nobodyworld/dev-agent-switchboard/issues/111)

**Initial implementation issues:** [#112](https://github.com/Nobodyworld/dev-agent-switchboard/issues/112), [#113](https://github.com/Nobodyworld/dev-agent-switchboard/issues/113), and [#114](https://github.com/Nobodyworld/dev-agent-switchboard/issues/114)

## Purpose

Switchboard currently coordinates high-level work through tasks, dependencies,
leases, heartbeats, and agent APIs. The next product stage adds a distinct
execution plane so deterministic validation can run on approved local workers
before a paid coding agent is used.

The first release is deliberately narrow. It validates one exact Git commit
with one named, versioned, read-only command manifest and returns structured
evidence. It is not a general remote shell, autonomous coding system, provider
router, or desktop RPA platform.

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

### Retain metadata longer than artifacts

Run metadata is persisted in the database. Artifacts are stored beneath the
configured Switchboard storage root in a run-owned directory.

The default artifact retention period is 14 days and is configurable. Metadata
may remain after artifact expiry so the audit record can explain what was
executed and why the underlying files are no longer available.

Normal API responses return bounded summaries and artifact metadata rather than
full logs. Artifact records include relative path, type, size, SHA-256 hash,
retention expiry, and redaction status.

### Redact before returning evidence

Workers use an explicit environment allowlist rather than inheriting every
parent-process variable. Secrets and configured patterns are redacted before
summaries leave the worker.

Full local logs may be retained as artifacts. Worker tokens, authorization
headers, secret environment values, and configured secret patterns must never
appear in normal result summaries.

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
- fixed argument-vector steps;
- working-directory rules;
- required capabilities;
- allowed environment keys and fixed values;
- network and repository-write policy;
- per-step and overall timeouts;
- output limits;
- artifact declarations;
- failure behavior;
- manifest digest.

A manifest step may be required or diagnostic-only. A required-step failure
normally stops later required execution.

### ExecutionRun

An execution run includes at least:

- work-order and worker references;
- attempt number;
- lease and heartbeat metadata;
- queued, assigned, started, and finished timestamps;
- terminal status and failing step;
- per-step evidence;
- environment fingerprint;
- cleanup status;
- artifact records;
- evidence fingerprint.

Only one active execution run may exist for a work order at a time.

## Worker Flow

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

## First End-to-End Target

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

Phase 1 is successful when an approved work order for an allowlisted repository
and exact SHA can be atomically assigned to one eligible local worker, executed
through one trusted read-only manifest, and returned as truthful structured
evidence without modifying the canonical checkout or consuming paid
coding-agent credits.
