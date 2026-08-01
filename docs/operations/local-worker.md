# Local execution worker operations

`scripts/local_worker.py` is the Phase 1 outbound-only worker for approved,
trusted execution manifests. It is not a remote shell: work orders never supply
an executable, a script body, an argv element, or a filesystem path.

## Install and configure

Install the repository's development requirements on the trusted workstation,
ensure `python` and `git` are on `PATH`, and set the Phase 1 credential in the
process environment:

```powershell
$env:SWITCHBOARD_ADMIN_TOKEN = "operator-provisioned-token"
python scripts/local_worker.py --config C:\worker\local-worker.json
```

Use `--once` for one deterministic checkout attempt:

```powershell
python scripts/local_worker.py --config C:\worker\local-worker.json --once
```

The token is deliberately excluded from the JSON file. Do not pass it on the
command line or place it in source control. Phase 1 reuses the admin token and
does not provide an individual worker-identity system.

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

## Runtime behavior and limits

Phase 1 is deliberately single-concurrency. Configuration must set
`max_concurrency` to exactly `1`; the worker advertises that same capacity and
will not take new work while draining or after shutdown begins.

Before creating a worktree, the worker checks the exact local trusted manifest,
name/version/digest, server-safe metadata, required capabilities, read-only
policy, network policy, timeout, and output limits. The reviewed executable
profiles are `worker-smoke@1` and `validate-switchboard@1`. The validation
profile runs fixed, shell-free Python version, dependency consistency, Ruff,
Black, Mypy, pytest-with-coverage, and Bandit steps. Dependency consistency is
diagnostic-only because it describes the operator's shared environment; all
other validation steps are required.

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

On POSIX, the worker uses a separate process session, sends `SIGTERM` to the
whole group, waits briefly, then sends `SIGKILL` if descendants remain. On
Windows it invokes the fixed internal `taskkill /PID <trusted-launched-pid> /T
/F` command with `shell=False`. No work-order value contributes to termination
arguments.

Artifact upload/download and server-side artifact-byte retention remain out of
scope. The server persists only compact evidence and verified artifact metadata;
reuse never transfers the retained bytes.
