# Local Execution Broker Architecture

**Status:** Accepted for Phase 1 implementation

**Parent epic:** [#111](https://github.com/Nobodyworld/dev-agent-switchboard/issues/111)

**Initial implementation issues:** [#112](https://github.com/Nobodyworld/dev-agent-switchboard/issues/112), [#113](https://github.com/Nobodyworld/dev-agent-switchboard/issues/113), and [#114](https://github.com/Nobodyworld/dev-agent-switchboard/issues/114)

## Purpose

Switchboard currently coordinates high-level work through tasks, dependencies,
leases, heartbeats, and agent APIs. The next product stage adds a distinct
execution plane so deterministic validation can run on approved local workers
before a paid coding agent is used.

This document describes the staged target across #112--#114, exact evidence
reuse in #121, and the first outbound GitHub adapter in #122. The #112 release
was deliberately narrower:
it persisted and validated control-plane contracts only. Worker execution and
evidence were added by #113 and #114. The resulting system is not a general
remote shell, autonomous coding system, provider router, or desktop RPA
platform.

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

### Local artifact retention and compact evidence (#114)

Issue #114 replaces the #112 placeholders with strict versioned evidence and
artifact records. Full files remain beneath a separate worker-configured,
run-owned evidence root. The worker verifies containment, regular-file status,
declared paths, byte limits, SHA-256 hashes, and deterministic expiry before it
reports metadata. Marker-verified pruning removes only expired owned children.

The evidence API returns bounded summaries and safe relative references rather
than full logs. It applies the explicit environment allowlist, configured
secret/pattern redaction, and absolute-path redaction before data leaves the
worker. A canonical JSON SHA-256 fingerprint binds the complete compact record.

### Reuse exact evidence only after worker-local proof (#121)

Reuse is explicit and read-only. `never` remains the default and always runs
the trusted manifest. `allow_exact` may skip validation only when every
deterministic result input matches and the source worker proves its retained
evidence locally; otherwise it executes once under the same live lease.
`require_exact` never executes validation and returns a bounded non-success
when exact proof is unavailable.

The versioned reuse identity is separate from the complete evidence
fingerprint. It binds repository and exact SHA, manifest identity and digest,
worker environment fingerprint, canonically sorted dependency-lock hashes,
result-affecting execution policy, and parser/artifact result contract. It
excludes run/work-order IDs, timestamps, durations, outcomes, cleanup text,
source provenance, and the complete evidence fingerprint.

The server uses that identity only to select a bounded, deterministic,
successful candidate on the same worker. The worker derives
`run-<source-run-id>` beneath its configured evidence root and rechecks the
exact ownership marker, local result identity, retention, regular-file and
non-reparse containment, declared size and SHA-256, and file stability. No
caller or server response supplies an absolute path. A reused execution is a
new run linked to the immutable source run and evidence fingerprint; it does
not copy bytes, extend retention, or mutate the source.

### Resolve exact pull-request heads and publish compact evidence (#122)

The first GitHub adapter is a server-side, synchronous translation layer. An
authenticated operator supplies only an allowlisted repository, pull-request
number, and trusted manifest identity. The adapter first resolves the configured
credential's stable actor identity, then resolves stable GitHub repository/PR
identity and one exact current head SHA. The actor, target, head, and manifest
bind one deterministic adapter request and normal pending work order. The
existing explicit approval, lease, worker, evidence, and repository-read-only
boundaries remain authoritative.

Immediately before publication, the server resolves the PR again. An unchanged
head can receive one bounded managed comment for the exact tested SHA; a moved
or unavailable head is marked stale and never receives a current-success
claim. The adapter persists comment ownership and recovers an ambiguous create
only after verifying configured-actor authorship, exact repository/PR
association, configured origin, and the deterministic marker. Bounded
newest-page recovery never follows supplied pagination URLs. A database-backed
expiring publication lease serializes remote writes across server processes;
stale attempts cannot finalize over a newer holder.

GitHub credentials remain server-only. The adapter does not fetch source or
give credentials/network access to the worker. The exact resolved commit object
must already exist in the operator-configured canonical repository. Missing
objects fail locally without SHA substitution or success evidence.

### Cheapest-capable routing remains local (#134)

Work orders use a versioned `routing_policy`: `first_available` by default or
explicit `cheapest_capable`. The default preserves existing capability-aware
first-poller behavior without requiring a routing profile. Cheapest-capable
routing still assigns only trusted outbound local workers. It does not invoke
a paid coding agent, integrate an AI provider, handle provider credentials,
query external rate limits, or make billing claims.

Each routed worker has a separate one-to-one operator-owned profile containing
enabled state, bounded integer estimated cost units, quota capacity and
remaining units, optional reset time, routing priority, and optimistic
revision. Workers cannot author these fields through registration or
heartbeat. The legacy floating `cost_ceiling` remains stored for compatibility
but is not authoritative; work orders use bounded integer
`maximum_cost_units` and `required_quota_units`. Cost units are abstract local
comparison values, not currency, credits, actual spend, or measured savings.

Every known-worker checkout records a server-time poll timestamp for that
requester. Heartbeat freshness proves liveness; poll freshness proves that the
outbound worker is still asking for work. Cheapest-capable eligibility also
requires online status, free capacity, manifest and work-order capabilities,
network compatibility, false repository-write capability, an enabled valid
profile, cost within the integer ceiling, and enough quota. Missing or
malformed profiles fail closed for cheapest-capable and do not affect unpinned
first-available work.

The exact deterministic score is:

1. lowest estimated cost units per run;
2. highest remaining quota after the prospective reservation;
3. lowest active-run/max-concurrency ratio using integer cross multiplication;
4. lowest operator routing-priority integer;
5. lexical stable worker ID.

An explicit `preferred_executor` is a hard pin to a known worker. It overrides
the score but none of approval, heartbeat, poll, status, capacity, capability,
network, read-only, cost, quota, or profile-enabled eligibility. An unavailable
pin never falls back to another worker.

Capacity reservation, conditional profile revision/quota reservation,
work-order claim, run creation, lease creation, and route provenance share one
database transaction. A lost conditional update rolls the whole attempt back.
The first valid owned run heartbeat changes reserved quota to consumed exactly
once. Pre-start cancellation or stale expiry releases reserved quota exactly
once and never above capacity. Once consumed, no terminal outcome or lease loss
refunds quota. A requeued order receives another reservation only when a new
attempt actually wins checkout. Profile replacements and quota resets use
optimistic revisions and are rejected while any reservation is active; reset
timestamps are monotonic and exact retries are idempotent.

The route assessment endpoint reads this state without reserving anything or
refreshing poll freshness. Assigned work orders and runs persist compact scalar
provenance, never candidate lists, complete profiles, local roots, machine user
names, commands, argv, logs, credentials, environment dumps, or private network
details. Result-affecting requested routing inputs participate in execution and
reuse policy identity; transient selected-worker cost/quota snapshots remain
route provenance and do not weaken exact same-worker evidence proof.

Provider budgets, external remaining-rate-limit ingestion, and paid-agent
routing remain later concerns. Deterministic local validation must not invoke a
paid coding agent.

### Operator validation command center (#136)

The dashboard adds a browser workspace over the accepted execution and GitHub
adapter boundaries; it does not create a second scheduler or execution path.
Lifecycle actions still call the explicit approve, queue, cancel, expire, and
publish routes. Only the selected active request is polled, with one replaceable
timer that is cleared when selection changes or the page unloads.

Server-owned projections assemble the operator view with bounded, stably ordered
queries. The browser does not join unbounded request, work-order, run, worker,
profile, evidence, and publication lists. History selects only the latest run
per adapter request and returns compact scalar provenance. Worker summaries
combine the declared worker with its operator-owned profile without exposing
capability dumps, local roots, or private connectivity data.

Adapter request identity binds every accepted result-affecting execution policy.
For compatibility, an all-default request may resolve the exact pre-#136 legacy
identity; that row and linked work order are returned unchanged. A non-default
request never uses legacy fallback. The linked work order remains the single
authoritative persistence location for reuse, routing, cost, quota, and preferred
executor policy, so no adapter schema migration is required.

Avoided-work metrics are projections, not a mutable savings ledger. One
successful reused run counts as one deterministic execution avoided. Reference
seconds are the non-negative persisted duration of its linked successful source
run, when available. Comparison units are the reused run's persisted route cost,
when available. These units are local routing comparisons only and are not money,
credits, provider usage, or verified spend reduction.

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
- preferred executor, legacy cost-ceiling metadata, routing policy, integer
  maximum cost, and required quota;
- explicit evidence-reuse policy and server-derived execution-policy hash;
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
- current status, last heartbeat, and server-maintained last checkout poll.

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
- strict artifact metadata and versioned compact evidence, including a
  deterministic fingerprint after #114 completion.
- compact server-owned route provenance and quota-reservation state after #134.

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

## Phase 1 End-to-End Flow (#113/#114)

```text
Connector or operator identifies a pull-request head SHA
    -> creates a read-only work order
    -> approves a trusted validation manifest
    -> eligible local worker pulls the run
    -> worker validates the exact SHA in an isolated checkout
    -> Switchboard returns compact evidence and artifact references
    -> connector reviews the evidence
```

Phase 1 exposes evidence for operator or connector review. Issue #122 adds one
manual outbound managed-comment publisher. It does not add GitHub event
ingestion, webhooks, polling, or check runs.

With #121, an opted-in assignment first derives its exact identity in the
detached checkout. Switchboard may return a same-worker candidate; local proof
then either creates a distinct reused run outcome without executing steps or
continues once through the normal fresh path. Lease heartbeat, cancellation,
expiry, ownership loss, and stale-completion rules remain unchanged.

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

### Phase 2A — GitHub exact-PR adapter

Tracked by #122:

- manual authenticated resolve/status/publish API;
- stable repository/PR identity and exact-head idempotency;
- one additive adapter lifecycle table linked to normal work orders/runs;
- immediate pre-publication head recheck;
- one bounded managed PR comment with current/stale truth;
- no source synchronization, webhooks, checks, or automatic approval.

### Phase 2B — Exact evidence reuse

Tracked by #121:

- explicit `never`, `allow_exact`, and `require_exact` policies;
- strict canonical reuse identity and exact indexed candidate selection;
- same-worker marker, result, artifact, hash, retention, and stability proof;
- distinct run provenance without artifact-byte transfer or source mutation;
- one lease-owned fresh fallback for `allow_exact` and no validation for
  `require_exact`.

### Phase 2C — Cheapest-capable trusted local routing

Tracked by #134:

- compatible `first_available` and explicit `cheapest_capable` policies;
- operator-owned integer cost/quota/priority profiles with optimistic revision;
- separate heartbeat and active-poll freshness;
- exact deterministic local-worker score and hard worker pins;
- atomic capacity, quota, claim, run, lease, and provenance persistence;
- reserve/consume/release/reset quota lifecycle;
- bounded route assessment and historical provenance APIs;
- no paid-agent or provider execution path.

### Later phases

- known-baseline failures;
- GitHub webhook ingestion and status/check integrations;
- GitHub Actions versus local-worker routing;
- MCP tools and secure outbound tunnel integration;
- provider budget and external rate-limit routing;
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
