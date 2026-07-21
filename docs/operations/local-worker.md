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
  "inherited_environment_keys": ["PATH", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP"],
  "redacted_key_patterns": ["TOKEN", "SECRET", "PASSWORD", "KEY"],
  "redacted_value_patterns": [],
  "poll_interval_seconds": 5,
  "heartbeat_interval_seconds": 15
}
```

Repository keys are logical `owner/repository` names. Their values are absolute,
operator-approved canonical Git checkout paths; a work order cannot select any
other path. The worker root must be absolute and must not equal, contain, or be
contained by a registered canonical checkout.

## Runtime behavior and limits

Phase 1 is deliberately single-concurrency. Configuration must set
`max_concurrency` to exactly `1`; the worker advertises that same capacity and
will not take new work while draining or after shutdown begins.

Before creating a worktree, the worker checks the exact local trusted manifest,
name/version/digest, server-safe metadata, required capabilities, read-only
policy, network policy, timeout, and output limits. Metadata-only
`validate-switchboard@1` is rejected in this phase. `worker-smoke@1` is the
only harmless executable proof profile.

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

## Logs, cleanup, cancellation, and restart

Each completed run retains its local directory beneath `worker_root`, including
`ownership.json`, `logs/*.stdout.log`, `logs/*.stderr.log`, and `result.json`.
Completion responses use relative `logs/...` references only. These files are
operator-owned Phase 1 diagnostics: Switchboard does not ingest them, and no
automatic retention job deletes them in this issue.

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

Issue #114 remains the boundary for durable server artifact ingestion,
operator-controlled retention processing, evidence fingerprints, and compact
evidence APIs.
