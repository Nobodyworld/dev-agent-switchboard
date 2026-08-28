# Operator validation lifecycle

> **PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY**

The owned validation lifecycle is the repository-supported way for a trusted
local operator to coordinate one exact Switchboard validation. It wraps the
existing FastAPI execution plane and outbound `LocalWorker`; it does not create
a second executor, add source-write authority, or turn the read-only workload
policy into operating-system isolation.

## Trust boundary and prerequisites

Use this command only on a trusted machine and with a trusted, already-present
canonical checkout. Before starting, provide:

- a clean checkout whose `origin` is the configured GitHub repository;
- the full 40-character commit already present as that checkout's `HEAD`;
- Python 3.11 or newer, Git, and every runtime required by the selected trusted
  manifest;
- strict Windows Job Object or POSIX process-group containment support;
- a new absent runtime root on a local, non-linked filesystem path;
- a free loopback port; and
- `SWITCHBOARD_ADMIN_TOKEN` in the current process environment.

Read-only workload policy prevents reviewed target commands from receiving
repository-write authority. It is not an OS account, ACL, container, VM,
network sandbox, or defense against a malicious trusted operator.

## Configuration and command

Store operator configuration in a private local JSON file. It contains local
paths but must never contain the token.

```json
{
  "schema_version": 1,
  "repository_full_name": "Nobodyworld/dev-agent-switchboard",
  "canonical_checkout": "X:\\path\\to\\clean-checkout",
  "target_sha": "0123456789abcdef0123456789abcdef01234567",
  "manifest_name": "validate-switchboard",
  "manifest_version": "1",
  "expected_manifest_digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "mode": "fresh-then-exact-reuse",
  "runtime_root": "X:\\new-runtime-root",
  "worker_id": "operator-validation-1",
  "worker_display_name": "Operator validation 1",
  "host": "127.0.0.1",
  "port": 8765,
  "routing_policy": "first_available"
}
```

Run interactively:

```powershell
$env:SWITCHBOARD_ADMIN_TOKEN = "<operator-provisioned-token>"
python scripts/dev.py validation-lifecycle --config <private-config.json>
```

For deliberate non-interactive use, fresh and reuse approval remain separate:

```powershell
python scripts/dev.py validation-lifecycle `
  --config <private-config.json> `
  --approve-fresh `
  --approve-reuse
```

`fresh-only` requires only `--approve-fresh`. Supplying or selecting a mode is
never itself approval.

The strict versioned model rejects unknown fields, abbreviated or uppercase
SHAs, malformed digests, unsupported modes or routing policies, non-loopback
hosts, unsafe ports, relative/traversal/device/network paths, existing roots,
linked or reparse ancestry, overlapping source/runtime roots, incompatible
limits, and out-of-contract timeouts. On Windows, the runtime-root text is
limited to 80 characters to reserve space for nested worktrees and target test
paths.

## Exact preflight

Preflight finishes before the runtime root or any process is created. It uses
fixed argv, `shell=False`, bounded output, and short timeouts to verify:

1. canonical Git repository and exact GitHub `origin` identity;
2. no staged, unstaged, or untracked source state;
3. exact `HEAD`, commit object, and tree snapshot without fetching;
4. trusted manifest name, version, digest, fixed steps, and read-only policy;
5. Python, Git, and manifest-required host runtime capabilities;
6. strict process containment support;
7. absent, distinct, non-overlapping, non-reparse local roots;
8. a currently available loopback port;
9. process-environment token presence, without serializing its value; and
10. bounded report sanitization availability.

Failure here creates no database, directory, process, work order, or report.

## Runtime ownership and processes

After complete preflight, the command creates the exact new runtime root and
atomically writes `operator-runtime.json` before any child directory. Marker
schema version 1 binds a random runtime ID, logical repository, exact SHA,
manifest identity and digest, lifecycle mode, `validation-lifecycle@1` command
identity, and creation time. It contains no path, token, argv, environment,
machine identity, or private network detail.

The marker then owns distinct database, server-storage, file-storage,
worker-source, retained-evidence, reports, TEMP, TMP, and process-record roots.
Normal execution refuses every existing root. Each later write or shutdown
signal revalidates the marker.

The command launches the reviewed server and `scripts.local_worker` with direct
fixed argv and a minimal environment. The token is passed only to child process
environments and the in-process typed API client. Private process records bind
the runtime ID, child kind, and held PID. Windows children use the existing Job
Object host; POSIX children use the existing process-group/session host.
Shutdown requests marker-owned graceful stop first and uses the held containment
object only if bounded drain fails. It never selects or terminates an unknown
PID. Final verification requires both children stopped and the port bindable.

The manual server and worker procedures in [Local worker
operations](local-worker.md) remain supported. The lifecycle only composes
those interfaces.

## Lifecycle modes and approvals

The machine report records monotonic phases. A failure can move only to owned
shutdown; it cannot resume later work.

```text
preflight_passed -> runtime_created -> server_healthy -> worker_online
fresh_created -> fresh_approval_required -> fresh_approved -> fresh_queued
fresh_running -> fresh_succeeded -> fresh_verified
reuse_approval_required -> reuse_created -> reuse_approved -> reuse_queued
reuse_succeeded -> reuse_verified
shutdown_started -> cleanup_verified -> completed
```

In interactive mode, fresh creation is followed by an exact typed confirmation
before approval. In reuse mode, the second confirmation occurs only after fresh
success, retained-evidence verification, source cleanup, zero leases, and zero
worker capacity; denial prevents reuse creation. Non-interactive flags record
the same two deliberate operator actions.

`fresh-only` submits `reuse_policy: never`, verifies the authoritative run,
route, exact manifest steps, local retained result, hashes, source snapshot,
leases, capacity, and cleanup, then shuts down.

`fresh-then-exact-reuse` performs that same fresh proof first. It then creates a
distinct `require_exact` work order on the same worker. Acceptance requires the
exact fresh source run and fingerprint, a second post-reuse local verification,
unchanged source retention expiry, zero reuse steps, zero reuse artifacts, no
fresh fallback, and clean final lease/capacity/process/port state. The report
states only the exact count of avoided deterministic steps; it makes no money,
credit, token, provider-cost, or financial-savings claim.

## Reports and privacy

The owned `reports` directory receives one versioned JSON report and one human
summary generated from the same model. The JSON has bounded strings,
collections, nesting, artifacts, and serialized bytes; oversize JSON fails
instead of being sliced. It may contain logical identities, full SHA/digests,
runtime/work-order/run/worker IDs, safe phases, approval state, route state,
step status/duration, artifact relative identity/size/hash, evidence
fingerprints, expiry, avoided-step count, and cleanup facts.

Recursive safe-text policy rejects absolute local paths. Reports exclude tokens
and token-shaped input, machine/user identity, raw environment, argv, commands,
HTTP bodies, database content, full logs, artifact bytes, raw exceptions, and
private network details. Private child output is capped, literal-token redacted,
and retained only under the owned runtime; it is never copied into the report.

## Failure preservation and read-only inspection

Every failure after marker creation preserves the entire runtime and writes one
bounded failed report when the report boundary remains trustworthy. The command
does not retry ambiguous creation/approval, create reuse after incomplete fresh
proof, repair database rows, expire leases, alter capacity, delete evidence,
resume a prior runtime, or clean uncertain paths or processes.

Inspect a preserved or successful owned runtime with:

```powershell
python scripts/dev.py inspect-validation-runtime <owned-runtime-root>
```

Inspection validates only the marker and optional bounded report. It does not
start processes, bind ports, migrate or query the database, approve work,
resume, retry, repair, clean, delete, or change timestamps. Foreign or malformed
state fails closed.

## Explicit exclusions

This command does not fetch target source; install tools; edit, stage, commit,
push, merge, or publish a target repository; add credentials or automatic
approval; add provider routing; start browser, Docker, Unity, GPU, desktop, RPA,
MCP, or tunnel workers; expose a public service; deploy; release; or make a
production-readiness claim.
