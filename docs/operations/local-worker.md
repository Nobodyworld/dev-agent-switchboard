# Local execution worker operations

`scripts.local_worker` is the Phase 1 outbound-only worker module for approved,
trusted execution manifests. It is not a remote shell: work orders never supply
an executable, a script body, an argv element, or a filesystem path.

## Install and configure

Install the repository's development requirements on the trusted workstation,
ensure `python` and `git` are on `PATH`, and set the Phase 1 credential in the
process environment:

```powershell
$env:SWITCHBOARD_ADMIN_TOKEN = "operator-provisioned-token"
python -m scripts.local_worker --config C:\worker\local-worker.json
```

Use `--once` for one deterministic checkout attempt:

```powershell
python -m scripts.local_worker --config C:\worker\local-worker.json --once
```

The token is deliberately excluded from the JSON file. Do not pass it on the
command line or place it in source control. Phase 1 reuses the admin token and
does not provide an individual worker-identity system.

Use the module form from a source checkout. Directly invoking
`python scripts/local_worker.py` does not establish the repository root on
Python's import path and can fail before registration with a package import
error. Worker configuration remains an operator trust decision: repository
mappings, the admin token, and approval must not be inferred or automated.

The operator-owned JSON configuration has strict JSON types. A minimal example
is:

```json
{
  "base_url": "https://switchboard.example",
  "worker_id": "trusted-workstation-1",
  "display_name": "Trusted workstation 1",
  "worker_root": "C:\\switchboard-worker",
  "evidence_root": "C:\\switchboard-evidence",
  "repositories": {
    "Nobodyworld/app-accounting-modular": "C:\\src\\app-accounting-modular",
    "Nobodyworld/dev-agent-switchboard": "C:\\src\\dev-agent-switchboard"
  },
  "max_concurrency": 1,
  "network_policy_capability": "worker_restricted",
  "execution_timeout_seconds": 120,
  "default_step_timeout_seconds": 60,
  "maximum_step_timeout_seconds": 3600,
  "output_summary_limit": 4096,
  "total_output_limit": 67108864,
  "disk_limit_bytes": 536870912,
  "evidence_retention_days": 14,
  "maximum_artifact_count": 128,
  "maximum_artifact_bytes": 67108864,
  "maximum_total_evidence_bytes": 536870912,
  "inherited_environment_keys": ["PATH", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP"],
  "redacted_key_patterns": ["TOKEN", "SECRET", "PASSWORD", "KEY"],
  "redacted_value_patterns": [],
  "poll_interval_seconds": 5,
  "heartbeat_interval_seconds": 15
}
```

Repository keys are logical `owner/repository` names. Their values are absolute,
operator-approved canonical Git checkout paths; a work order cannot select any
other path. The worker and evidence roots must be distinct absolute
operator-owned paths. Neither may overlap a registered canonical checkout, and
the evidence store also rejects overlap with the disposable source run
directory. Evidence policy accepts retention from 1 through 3,650 days, at most
128 artifacts, and bounded per-artifact and total byte limits; the total must
cover the per-artifact limit.

At registration the worker sends only the sorted logical keys as
`repository_full_names`. Switchboard rejects unknown, duplicate, unsorted,
empty, or oversized declarations. Paths remain workstation-local. A worker is
ineligible for either routing policy, hard pins, assessment, fresh execution,
and exact reuse unless it advertises the exact work-order repository. This is
only an early eligibility signal: exact local-object and containment checks
remain authoritative on the worker.

For GitHub exact-PR requests, the adapter resolves identity but does not fetch
source. The exact resolved head commit object must already exist in this
configured canonical repository. The worker runs a local `git cat-file` check
before creating its disposable worktree and never fetches, adds a remote,
writes a ref, or substitutes another SHA. A missing object fails the run with
`requested_sha_not_available_locally`, produces no success evidence, and
leaves the canonical repository unchanged. Fork heads follow the same rule.
See
[GitHub exact pull-request validation](github-exact-pr-validation.md)
for the operator workflow.

The dashboard's [Validation command center](validation-command-center.md)
provides the same request, approval, routing-profile, lifecycle, evidence, and
publication operations through bounded server projections. It does not change
the worker's outbound-only pull loop, trust model, repository mapping, or local
evidence retention rules.

## Supported local validation lifecycle

The complete supported command, strict configuration, lifecycle phases,
privacy contract, failure preservation, and exclusions are documented in the
[operator validation lifecycle guide](operator-validation-lifecycle.md).

For one exact, clean Switchboard checkout, the repository-supported operator
command can own the local server, outbound worker, fresh validation, and optional
same-worker exact reuse as a single fail-closed lifecycle:

```powershell
$env:SWITCHBOARD_ADMIN_TOKEN = "operator-provisioned-token"
python scripts/dev.py validation-lifecycle --config operator-lifecycle.json
```

Selecting `fresh-only` or `fresh-then-exact-reuse` in the configuration is not
approval. At an attended terminal the command displays the bounded logical
identity and requires the exact confirmation separately for fresh and reuse.
Deliberate non-interactive callers must provide `--approve-fresh` and, when
reuse is selected, the distinct `--approve-reuse` flag. Reuse approval is not
requested until the fresh run, compact evidence, retained evidence, cleanup,
route, exact source, and zero-lease state have all passed.

A minimal configuration is:

```json
{
  "schema_version": 1,
  "repository_full_name": "Nobodyworld/dev-agent-switchboard",
  "canonical_checkout": "D:\\operator\\dev-agent-switchboard",
  "target_sha": "0123456789abcdef0123456789abcdef01234567",
  "manifest_name": "validate-switchboard",
  "manifest_version": "1",
  "expected_manifest_digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "mode": "fresh-then-exact-reuse",
  "runtime_root": "D:\\operator-runtimes\\switchboard-validation-001",
  "worker_id": "operator-validation-1",
  "worker_display_name": "Operator validation 1",
  "host": "127.0.0.1",
  "port": 8765,
  "routing_policy": "first_available"
}
```

Both local paths must be absolute. The canonical checkout must be a clean Git
checkout at exactly `target_sha` with the expected GitHub `origin`; the runtime
root and all of its descendants must be absent. The host must be loopback. The
Windows runtime-root text must be at most 80 characters so the fixed worker
layout still reserves space for nested Git worktrees and target test paths. The
normal command rejects existing, overlapping, linked, junction, reparse-point,
malformed, unknown, unsupported, occupied, or identity-mismatched state before
runtime creation. It does not fetch, repair, clean, reset, stash, edit the
database, or accept a different commit.

After read-only preflight, the command creates the runtime root, writes a random
versioned ownership marker before any child directory, and then creates private
database, server storage, file storage, disposable source, retained evidence,
temporary, process-record, and report areas. The bearer token is read only from
the process environment, passed only to owned child environments and the
in-process API client, and omitted from configuration, argv, markers, process
records, reports, and safe console failures. Server and worker processes run
under the existing strict containment host. Graceful marker-based drain is
attempted first; fallback termination targets only the still-held containment
object for that direct child.

Machine JSON and human text reports are generated from one bounded path-free
model under the runtime's private `reports` directory. Oversize or unsafe report
content is a failure, never silently truncated. A failure after marker creation
preserves the runtime and writes a failed report when the report boundary itself
remains trustworthy. Normal execution never resumes, repairs, or cleans a prior
runtime.

Read-only inspection is a separate command:

```powershell
python scripts/dev.py inspect-validation-runtime D:\operator-runtimes\switchboard-validation-001
```

Inspection validates the root marker and, when present, its bounded report. It
does not create directories, touch timestamps, bind ports, start processes,
approve work, query mutable control-plane state, or repair anything. A malformed
or foreign marker/report fails closed.

## Runtime behavior and limits

Phase 1 is deliberately single-concurrency. Configuration must set
`max_concurrency` to exactly `1`; the worker advertises that same capacity and
will not take new work while draining or after shutdown begins.

Before creating a worktree, the worker checks the exact local trusted manifest,
name/version/digest, server-safe metadata, required capabilities, read-only
policy, network policy, timeout, and output limits. The reviewed executable
profiles are `worker-smoke@1`, `validate-switchboard@1`,
`validate-accounting-modular@1`, `validate-zscripts@1`, and
`validate-industry-resilience@1`. The Switchboard validation
profile runs fixed, shell-free Python version, dependency consistency, Ruff,
Black, Mypy, pytest-with-coverage, and Bandit steps. Dependency consistency is
diagnostic-only because it describes the operator's shared environment; all
other validation steps are required.

The accounting profile mirrors eleven reviewed Python quality steps: Ruff
lint/format, bounded Mypy, full pytest branch coverage, aggregate and critical
coverage gates, focused accounting controls, `pip check`, locked runtime and
development dependency audits, and the repository secret scanner. It requires
Python 3.12+, Git, a read-only worker, and three reviewed dependency inputs.
Docker and attended browser gates remain separate worker types.

The two external profiles are compiled from reviewed typed Switchboard source;
no worker configuration, API request, database row, target file, or YAML can
author a command. `validate-zscripts@1` runs exactly
`python scripts/quality_gate.py quality` and requires Python 3.11+, Node
24.12.0+, and pnpm exactly 10.18.1. It accepts only the fixed regular JSON
reports `reports/quality-summary.json`, `reports/coverage.json`, and
`reports/diagnostics.json`. The parser opens only the declared
`quality-summary.json` result source and validates its closed ordered operation
inventory, passed statuses, coverage details and threshold, and diagnostics
success. The separate coverage and diagnostics files remain containment-checked,
size-bounded, hashed retained evidence; they are not hidden parser inputs and
their bodies are not returned to the server.

`repository_write_policy=read_only` is a reviewed work-order policy and
canonical-integrity detection, not an operating-system sandbox. The target runs
under the worker account in a writable disposable checkout. Operators must use
a least-privilege worker identity without canonical-source or publication
credentials, and use a container, ACL, or read-only mount when filesystem
prevention is required. Likewise, ordinary process-group cleanup is not a
substitute for platform-managed process containment.

`validate-industry-resilience@1` requires Python 3.13+ and runs ten direct
reviewed steps: Python version, `pip check`, Black, Ruff, Mypy, required
runtime coverage at 85% for `src/adapters`, `src/agents`, `src/application`,
`src/core`, `src/extensions`, `src/infrastructure`, `src/interfaces/api`, and
`src/interfaces/streamlit` (term-missing plus XML and JSON reports),
informational full-`src` coverage, benchmark metrics, one combined
`pip_audit` JSON report at `build/reports/pip-audit.json`, and
`detect_secrets.pre_commit_hook --baseline config/.secrets.baseline`. The final
step validates the declared baseline only; it is not a source secret scan. The
profile does not require GNU Make and does not claim Docker, Edge, Playwright,
screen-reader, release, publication, data-refresh, or provider acceptance.

Node and pnpm capability discovery uses only fixed `node --version` and
`pnpm --version` calls with `shell=False`, a short timeout, and bounded output.
Node's leading `v` is normalized; a missing or non-exact pnpm tool makes a
Zscripts worker ineligible rather than triggering installation or fallback.
For factory profiles, the worker enforces the stricter of its local evidence
limits and the reviewed retention/count/byte ceilings. Factory result contracts
and result-affecting input hashes bind exact reuse, while legacy manifest
digests and evidence behavior remain unchanged.

For each owned run, the worker creates a detached exact-SHA checkout underneath
the worker root. Its generated `ownership.json` binds the worker, server run,
random run identity, canonical repository, and SHA. The worker refuses symlink,
junction, reparse-point, root-overlap, marker-mismatch, and outside-root
cleanup layouts. The canonical checkout's branch/HEAD, staged and unstaged
changes, untracked status, and tracked tree are checked before and after the
disposable lifecycle.

Only reviewed fixed argv tuples run with `shell=False`. The environment starts
from the configured inherited-key allowlist, then receives fixed manifest
values. Completion data records redacted, bounded summaries; it never includes
the admin token or a complete inherited environment.

The worker keeps result data structured until final JSON serialization and
applies an 8,000-character API-summary limit. When needed, it progressively
compacts only stdout/stderr summaries and sets
`result_summary_truncated: true`; SHA, step identity/status, exit code,
duration, terminal reason, truncation state, log references, and safe
environment summaries remain present. Serialized JSON text is never sliced.

`worker_restricted` means an operator-controlled trusted network posture. It
does **not** claim per-process network isolation or a firewall sandbox. Select
`disabled` only when the worker can truthfully support that policy.

## Cheapest-capable local routing

Work orders default to `routing_policy: first_available`; existing workers and
callers need no routing profile for unpinned work. An operator may instead
choose `cheapest_capable` with optional integer `maximum_cost_units`, integer
`required_quota_units`, and an optional hard `preferred_executor` worker ID.
The legacy floating `cost_ceiling` field remains compatible but does not
control this policy. Cost units are abstract values chosen by the local
operator. They are not dollars, credits, actual spend, savings, or a provider
rate-limit balance.

Before queueing cheapest-capable work, register the worker normally and create
its profile through the privileged execution API. A profile contains an
enabled flag, estimated integer cost per run, quota capacity and remaining
units, optional timezone-aware reset timestamp, routing priority, and revision.
Worker registration and heartbeat payloads reject those fields, so the worker
cannot make itself cheaper or increase its quota. Replace a profile or reset
quota only with the exact expected revision returned by the latest read. A
stale revision returns `409` without changing state. Switchboard rejects
profile replacement and reset while a run has reserved, not-yet-consumed
quota. Reset retries with the same timestamp and value are idempotent; older or
conflicting resets fail closed.

Cheapest-capable candidates must have both a fresh heartbeat and a fresh
server-recorded checkout poll. Every authenticated checkout attempt by a known
worker refreshes only that worker's poll timestamp. Route assessment does not.
Keep `poll_interval_seconds` safely below
`SWITCHBOARD_EXECUTION_ACTIVE_POLL_FRESHNESS_SECONDS` (default `60`) and keep
worker heartbeats within
`SWITCHBOARD_EXECUTION_HEARTBEAT_FRESHNESS_SECONDS` (default `300`). A worker
that keeps heartbeating but stops checkout polling ages out, allowing another
active poller to proceed.

Among fully eligible active workers, Switchboard ranks lowest estimated cost,
then highest quota headroom after reservation, lowest active-load ratio, lowest
routing priority, and lexical worker ID. Load ratios use integer cross
multiplication. A preferred executor overrides ranking only: it must already be
known and still pass approval, profile enabled, heartbeat, poll, status,
capacity, manifest/work-order capabilities, network, repository-read-only,
cost, and quota checks. An unavailable pin does not fall back to another
worker.

On a successful checkout, capacity, quota, work-order claim, run, lease, and
route provenance commit atomically. The first valid owned run heartbeat consumes
reserved quota exactly once. Cancellation or stale expiry before that heartbeat
releases it exactly once. Once consumed, success, failure, timeout,
cancellation, lease loss, and requeue do not refund it. Requeued work reserves
again only after a new attempt actually wins checkout. Common bounded
non-assignment reasons include `better_candidate_active`,
`preferred_executor_unavailable`, `routing_profile_missing`,
`routing_profile_disabled`, `worker_heartbeat_stale`,
`worker_checkout_poll_stale`, `routing_cost_ceiling_exceeded`,
`routing_quota_insufficient`, and `routing_reservation_conflict`.
Repository mismatches include `worker_repository_unavailable` and occur before
capacity or quota reservation.

Use `GET /api/execution/work-orders/{id}/route-assessment` before assignment to
inspect the current bounded decision without reserving or refreshing polls.
After assignment, the work-order and run responses and their `/route` endpoints
show compact provenance: policy, selected worker/profile revision, estimated
cost, required/reserved quota, reservation state, eligible count, pin flag,
reason, and decision timestamp. They never include candidate lists, full
profiles, local roots, machine user names, commands, argv, logs, secrets,
credentials, environment dumps, or private network details.

This routing path is still the same outbound-only local worker. It does not
execute a paid coding agent, contact an AI provider or billing API, accept
provider credentials, or add an inbound workstation listener.

## Evidence, retention, and privacy

Each admitted run creates exactly one `run-{server_run_id}` directory beneath
`evidence_root`. Its `ownership.json` records schema version, worker ID, run ID,
creation time, and deterministic retention expiry. Full stdout/stderr logs and
`result.json` remain in this marked directory after source cleanup. Artifacts
are accepted only from trusted manifest declarations, must be contained regular
non-reparse files, are streamed through size limits and SHA-256 hashing, and are
recorded with relative POSIX paths.

Declared files produced in the disposable checkout are copied into the marked
worker-owned evidence directory before hashing. Existing evidence logs are
reused. Missing, oversized, non-regular, symlink/reparse, or escaping sources
fail artifact finalization; the canonical repository is never the artifact
target.

The worker checks expired evidence at startup and before idle checkout. It
deletes only direct child directories whose valid ownership marker names the
same worker and whose expiry is due. Missing, malformed, foreign, nested, or
reparse-point layouts are preserved and surfaced as failures for operator
inspection. There is no independent background scheduler.

`GET /api/execution/runs/{run_id}/evidence` returns the strict compact record:
exact repository/SHA, manifest identity and digest, safe worker environment
identity, dependency-lock hashes, step outcomes and parsed summaries, artifact
hashes and expiry, cleanup state, and the canonical fingerprint. It never
returns artifact bytes or full logs. API summaries apply configured key/value
redaction plus absolute-path redaction. Local logs have `redaction_state: none`:
they can contain tool output and must be protected as operator-private data.

If evidence pruning fails, stop the worker, inspect the exact reported child
under `evidence_root`, correct its ownership or filesystem condition manually,
and restart. Never bulk-delete the root. If artifact finalization or local
result writing fails while ownership remains, the worker reports a truthful
failed terminal result and preserves safe diagnostic files.

### Exact evidence reuse

Work orders default to `reuse_policy: never`. For `allow_exact` or
`require_exact`, the assigned worker first creates the normal live run and
exact-SHA disposable checkout, then derives a versioned identity from the
trusted manifest, current safe environment fingerprint, declared dependency
locks, and server-derived execution policy. The worker cannot accept a
caller-selected source run, worker, fingerprint, filename, command, or path.

When Switchboard returns a bounded same-worker candidate, the worker derives
the source directory internally as `run-<source-run-id>` beneath
`evidence_root`. It verifies the exact ownership marker, immutable local result
identity and complete evidence fingerprint, original non-expired retention,
and every declared artifact. Each file must remain contained, regular,
non-symlink/non-reparse, within configured count and byte limits, and stable
across size and SHA-256 verification. Missing, pruned, changed, malformed,
foreign-worker, traversal-shaped, device-shaped, or ambiguous evidence fails
closed; no artifact bytes or local paths are returned to the server.

A verified reuse executes no validation step. The new run records the decision,
identity/hash, source run ID, and source evidence fingerprint while leaving the
source directory and expiry unchanged. `allow_exact` performs at most one
fresh execution after failed proof while the same lease remains live.
`require_exact` performs no validation and completes with a bounded non-success
reason when proof cannot be obtained. Cancellation, heartbeat, lease expiry,
ownership loss, and stale-completion suppression apply during lookup,
verification, and fallback exactly as they do during fresh execution.

## Source cleanup, cancellation, and restart

The disposable `checkout` is removed through its exact registered
`git worktree remove --force` entry. The worker never runs a global
`git worktree prune`, so unrelated worktree metadata is untouched. A cleanup or
canonical-integrity failure changes an otherwise successful terminal result to
a truthful failure while retaining the run record for diagnosis.

If `result.json` cannot be written, the failure cannot suppress the owned
completion request. An otherwise successful run becomes failed with
`local_result_record_failed`; an existing execution failure keeps its original
terminal reason and the additional record failure appears in bounded cleanup
metadata. Completion is attempted once and is not blindly retried.

Before compact result JSON is submitted, the worker recursively replaces
literal backslashes with `[BACKSLASH]` and complete local `sqlite:///` or
`sqlite+aiosqlite:///` DSNs with `[LOCAL_DATABASE_URI]`. This remote-evidence
sanitization does not rewrite the full retained logs: those bytes remain local
under the existing ownership, containment, and retention policy. The server
continues to reject raw local database URIs, `file:` URIs, and genuine absolute
paths submitted directly or inside nested completion/evidence values.

Non-ownership HTTP failures use a bounded typed diagnostic. It retains the
status code, one stable reason, and at most eight validation entries containing
only bounded safe location, type, and sanitized message fields. It never retains
the raw response, request body, validation `input`, arbitrary validation
context, authorization value, HTML, local path, or local database URI.

While a step runs, the worker sends worker and run heartbeats, watches the
overall deadline, and reacts to shutdown. Worker liveness and run ownership are
independent: a transient worker-heartbeat failure does not suppress the run
heartbeat. The validated run-heartbeat response is the current authoritative
state. A lost lease, `404`/`409` run heartbeat, or server-terminal state cancels
the local process tree and suppresses stale success. Malformed or unsupported
run-heartbeat data fails closed with `invalid_run_heartbeat`; while ownership
has not been explicitly lost, the worker may send one truthful cancelled
completion. A transient run-heartbeat transport failure waits until the next
normal interval rather than retrying immediately.

Shutdown that arrives after server checkout but before local admission sends
one cancellation with `worker_shutdown_before_start` and cleanup
`not_started`. Unexpected local concurrency rejection uses
`local_concurrency_rejected_after_checkout`. Neither path creates a worktree or
starts a process, and ownership loss during completion is treated as an
already-disposed lease. Overall deadline and later operator shutdown are
reported as timeout/cancellation while ownership is known. Restart never
infers lease ownership from residual run directories and never executes a local
run ID twice in one worker process.

Legacy manifests use a separate process session on POSIX and the fixed internal
Windows tree-termination path; no work-order value contributes to those
termination arguments. Factory profiles use a stricter, gated execution host:

- On Windows, the worker creates a non-breakaway Job Object with
  `KILL_ON_JOB_CLOSE`, assigns the blocked trusted host before it receives the
  reviewed argv, and terminates the Job Object for cancellation or deadlines.
- On Linux, the trusted host becomes a child subreaper before it accepts the
  reviewed argv. It terminates the target process group and checks/reaps
  adopted descendants, including a target child that called `setsid()`, before
  it returns control to parser or evidence code.

If strict quiescence cannot be proved, Switchboard does not parse/capture target
outputs, write a local result record, or recursively clean the target-owned
worktree or evidence directory. It records a bounded containment/cleanup state
for operator recovery instead. This is process containment for the reviewed
workload, not a replacement for the least-privilege filesystem isolation
boundary described above.

> [!WARNING]
> The strict host is defense in depth, not an execution sandbox. In particular,
> it does not separate a public target from the worker OS identity, the worker's
> bearer token, writable canonical Git metadata, or other same-account process
> state. Linux subreaping cannot contain every kernel-parentage escape, and a
> Windows Job Object does not create an account or filesystem boundary. Do not
> use a worker that shares any source, publication, or control-plane credential
> with a live public target. Live external dogfood requires an operator-managed
> separate least-privilege identity plus a container, VM, or equivalent ACL/
> mount boundary; absent that boundary, use only committed synthetic fixtures.

> [!IMPORTANT]
> A `source_quiescence_failed` result drains the worker. Retain its run directory
> and investigate or terminate the surviving process, or discard the worker
> host/VM. Restarting the Python worker alone does not prove that an orphaned
> same-account process is gone.

Artifact upload/download and server-side artifact-byte retention remain out of
scope. The server persists only compact evidence and verified artifact metadata;
reuse never transfers the retained bytes.

## Revocation and external dogfood boundaries

To stop accepting a workload, remove or replace its reviewed source mapping and
deploy that reviewed change, then remove the corresponding local repository key
or stop affected workers. Do not edit a historical manifest or bulk-delete
evidence to simulate revocation: those records remain immutable proof of the
prior run. A rollback restores a previously reviewed profile/catalog revision
and still requires current capability and exact-SHA checks.

Synthetic acceptance fixtures in Switchboard CI prove the worker and server
path only; they never fetch or execute external target source. Live dogfood is
separate. Zscripts PR #119 is merged, so its approved disposition is
`TARGET-STATE-BLOCKED` and no replacement PR may be substituted. Industry
Resilience PR #130 can be live-dogfooded only after its state/head are
re-resolved and an operator supplies an approved canonical checkout containing
that exact object. Without that checkout, record the blocker and do not clone,
fetch, or claim live evidence.
