# Operator validation lifecycle

> **PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY**

The owned validation lifecycle is the repository-supported way for a trusted
local operator to coordinate one exact validation of a selected allowlisted
repository. It wraps the
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
  "target_sha": "<40-hex-target-sha>",
  "manifest_name": "validate-switchboard",
  "manifest_version": "1",
  "expected_manifest_digest": "<64-hex-manifest-digest>",
  "mode": "fresh-then-exact-reuse",
  "runtime_root": "X:\\new-runtime-root",
  "worker_id": "operator-validation-1",
  "worker_display_name": "Operator validation 1",
  "host": "127.0.0.1",
  "port": 8765,
  "routing_policy": "first_available"
}
```

Check the configuration before creating a runtime, then run interactively:

```powershell
$env:SWITCHBOARD_ADMIN_TOKEN = "<operator-provisioned-token>"
python scripts/dev.py validation-preflight --config <private-config.json>
python scripts/dev.py validation-lifecycle --config <private-config.json> --format human --progress
```

For deliberate non-interactive use, fresh and reuse approval remain separate:

```powershell
python scripts/dev.py validation-lifecycle `
  --config <private-config.json> `
  --approve-fresh `
  --approve-reuse
```

`fresh-only` requires only `--approve-fresh`. Supplying or selecting a mode is
never itself approval. A non-interactive input stream without the required
approval flag is denied without waiting for input. Interactive prompts are
written to stderr, including in JSON mode.

The strict versioned model rejects unknown fields, abbreviated or uppercase
SHAs, malformed digests, unsupported modes or routing policies, non-loopback
hosts, unsafe ports, relative/traversal/device/network paths, existing roots,
linked or reparse ancestry, overlapping source/runtime roots, incompatible
limits, and out-of-contract timeouts. On Windows, the runtime-root text is
limited to 80 characters to reserve space for nested worktrees and target test
paths.

The repository identity is compared semantically and case-insensitively, while
the configured logical spelling remains the report spelling. Supported origins
are HTTPS, SCP-style SSH, and `ssh://` GitHub forms with user `git`; `.git` and
one terminal slash are optional. HTTP, HTTPS userinfo, SSH users other than
`git`, ports, query/fragment data, lookalike hosts, alternate repositories,
extra path components, encoded or literal traversal, file URLs, and local paths
are rejected without copying the raw origin into a failure or report.

## Read-only readiness and exact preflight

`validation-preflight` performs the authoritative execution checks without
creating an owned runtime. It defaults to human output; request a bounded
machine result with:

```powershell
python scripts/dev.py validation-preflight --config <private-config.json> --format json
```

Its version-1 result reports the safe configured logical identity, stable
check and failure codes, and applicable configured/required timeout facts.
Each check is `pass`, `fail`, or `not_checked` with an explicit `checked`
boolean. If a prerequisite fails, later checks remain `not_checked`; they are
never presented as passed. An invalid configuration cannot supply a trusted
identity and does not cause the remaining checks to run.

Readiness is a point-in-time observation. It creates no runtime, database,
server, worker, work order, approval, or report, and reserves no port or source
state. A passing result is not execution authorization. The lifecycle reruns
the same authoritative checks immediately before execution; source changes,
an occupied port, or another changed prerequisite can invalidate earlier
readiness.

Preflight finishes before the runtime root or any server or worker process is
created. Its read-only tool probes use fixed argv, `shell=False`, bounded
output, and short timeouts to verify:

1. the strict configuration contract and safe public identity fields;
2. supported Python runtime;
3. strict process containment support;
4. absent, distinct, non-overlapping, non-reparse local roots;
5. the trusted internal Switchboard control-plane source;
6. a currently available loopback port;
7. process-environment token presence, without serializing its value;
8. canonical Git repository, matching GitHub `origin`, clean source, exact
   `HEAD`, commit object, and tree snapshot without fetching;
9. trusted manifest name, version, digest, fixed steps, and read-only policy;
10. manifest/step execution and terminal-observation timeout compatibility; and
11. Git and manifest-required host runtime capabilities.

Failure here creates no owned runtime, database, server, worker, work order,
or report.

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
signal revalidates the complete original marker identity.

Marker verification rejects root, parent, ancestry, or marker symlink,
junction, and reparse state. It opens only a bounded regular marker, requests
no-follow behavior where supported, compares the file identity before open,
through the descriptor read, and after close, decodes strict UTF-8 JSON,
rejects duplicate or unknown keys, and compares every marker field to the
`RuntimeSummary` captured at creation. Process records, worker configuration,
private diagnostics, stop files, fallback termination, finalization, cleanup,
and both report writes all call that same verifier immediately before their
action. If identity is missing, changed, malformed, unstable, or ambiguous,
the command performs none of those actions and preserves the runtime and held
process state for diagnosis.

The command derives Switchboard's control-plane root internally from the loaded
operator package, rejects linked or incomplete roots, and requires the reviewed
`scripts.operator_server`, `scripts.local_worker`, server, and worker modules.
It launches those modules with that root as both `cwd` and the sole
`PYTHONPATH` source. The selected target checkout is used only by the worker's
logical repository mapping; target contents never supply control-plane imports
or launchers. The command uses direct fixed argv and a minimal environment. The
token is passed only to child process
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

Add `--progress` to observe bounded transitions on stderr. Progress covers
startup, fresh and reuse approval boundaries, work-order/run observations,
evidence verification, shutdown, and cleanup only when the lifecycle has
actually reached or observed them. It does not infer running work from queue
creation or invent completion from elapsed time. At most 64 events use a
closed vocabulary and safe bounded fields; progress contains no local paths,
argv, credentials, raw response bodies, or logs.

Progress is optional and has no execution authority. Observer or output
failure cannot grant approval, create a retry, replace verification, change
the lifecycle outcome, or prevent the required owned shutdown path. The
final verified report remains the evidence of outcome and cleanup.

`fresh-only` submits `reuse_policy: never`, verifies the authoritative run,
route, exact manifest steps, local retained result, hashes, source snapshot,
leases, capacity, and cleanup, then shuts down. Success always requires the
persisted reuse/result identity and its matching SHA-256 identity hash, local
result identity equality, evidence fingerprint, ownership marker, stable
contained result record, resolved-contained regular non-reparse artifacts,
exact sizes and SHA-256 hashes, and valid unchanged retention. The exact same
retained-evidence verifier is mandatory in both modes; `fresh-only` has no
reduced identity path.

`fresh-then-exact-reuse` performs that same fresh proof first. It then creates a
distinct `require_exact` work order on the same worker. Acceptance requires the
exact fresh source run and fingerprint, a second post-reuse local verification,
unchanged source retention expiry, zero reuse steps, zero reuse artifacts, no
fresh fallback, and clean final lease/capacity/process/port state. The report
states only the exact count of avoided deterministic steps; it makes no money,
credit, token, provider-cost, or financial-savings claim.

Every accepted route proves exactly `first_available`, the configured worker,
an explicit pin, zero required and reserved quota units,
`quota_reservation_state: not_required`, a bounded route reason, and at least
one eligible candidate. `consumed`, any nonzero quota, a different worker, or a
different policy fails verification.

## Reports and privacy

All three operator commands accept `--format human|json`. `validation-preflight`
defaults to `human`; `validation-lifecycle` and `inspect-validation-runtime`
default to `json` for compatibility. Machine stdout contains one bounded JSON
object for success or failure. Prompts, opt-in progress, human diagnostics,
and the stored-inspection notice use stderr in JSON mode.

Successful lifecycle JSON remains the existing schema-version-2 report.
Readiness success and expected configuration/check failures use its own
version-1 readiness result. Usage errors, interruption, or unexpected command
errors use the command-error envelope, as do lifecycle and inspection
failures. This version-1 object contains
`kind: operator-command-error`, `command`, `outcome: failed`, a stable `reason`,
and reviewed `guidance`. Human output derives from the same validated models.
Presentation does not change stored historical report schemas or records.

A broken stdout channel cannot deliver a JSON result. The command exits with
status 1 and attempts a fixed diagnostic on stderr. Final-output failure is
handled after the lifecycle's required owned shutdown and cannot bypass it.

The owned `reports` directory receives one schema-version-2 JSON report and one human
summary generated from the same model. The JSON has bounded strings,
collections, nesting, artifacts, and serialized bytes; oversize JSON fails
instead of being sliced. It may contain logical identities, full SHA/digests,
runtime/work-order/run/worker IDs, safe phases, approval state, route state,
step status/duration, artifact relative identity/size/hash, evidence
fingerprints, expiry, avoided-step count, and cleanup facts.
Each verified run also retains its reuse/result identity hash, source run ID,
route policy and reason, required and reserved quota, reservation state,
eligible-candidate count, exact artifact total bytes, evidence fingerprint, and
expiry. Artifact total bytes must equal the sum of the verified artifact
records. Both serializers invoke the same run validator.

Recursive safe-text policy rejects absolute local paths. Reports exclude tokens
and token-shaped input, machine/user identity, raw environment, argv, commands,
HTTP bodies, database content, full logs, artifact bytes, raw exceptions, and
private network details. Private child output is capped, literal-token redacted,
and retained only under the owned runtime; it is never copied into the report.

## Actionable diagnostics

Failures pair a stable bounded reason with fixed operator guidance. The
guidance names the category to review without repeating private input or
performing a fix:

| Failure category | Operator action |
| --- | --- |
| Missing process token | Provision the existing admin token in the invoking process environment; keep its value out of configuration and output. |
| Unavailable runtime, tool, or containment | Check the selected manifest's supported host requirements and the operator's local toolchain. |
| Dirty or wrong source | Review the selected canonical checkout, logical repository, and exact commit before another attempt. |
| Unsafe or existing runtime root | Select a new absent, non-overlapping root with safe ancestry; preserve existing runtime evidence. |
| Occupied loopback port | Review the configured port and choose an available approved loopback endpoint. |
| Manifest/worker timeout mismatch | Review the configured worker limits against the selected manifest's required execution budget. |
| Terminal observation budget mismatch | Review the observation timeout against the full required execution and finalization budget. |

Unknown or unsafe failure text is replaced by bounded generic guidance.
Neither readiness nor diagnostics fetches source, installs tools, supplies
credentials, edits configuration, releases occupied ports, approves work, or
automatically retries execution.

## Failure preservation and read-only inspection

Every failure after marker creation preserves the entire runtime and writes one
bounded failed report when the original marker identity and report boundary
remain trustworthy. Marker ownership loss forbids report creation or overwrite.
The command
does not retry ambiguous creation/approval, create reuse after incomplete fresh
proof, repair database rows, expire leases, alter capacity, delete evidence,
resume a prior runtime, or clean uncertain paths or processes.

Inspect a preserved or successful owned runtime with:

```powershell
python scripts/dev.py inspect-validation-runtime <owned-runtime-root> --format human
```

Human output begins with `stored state only; live evidence not reverified`.
The default JSON mode preserves the existing stored-inspection schema and
writes that same notice to stderr, outside its single stdout object.

Inspection validates only the marker and optional bounded report. A stored
success describes the earlier run; inspection does not rehash retained
artifacts or prove present evidence, live processes, port availability, leases,
capacity, or current source integrity. It does not
start processes, bind ports, migrate or query the database, approve work,
resume, retry, repair, clean, delete, or change timestamps. Foreign or malformed
state fails closed.

## Explicit exclusions

This command does not fetch target source; install tools; edit, stage, commit,
push, merge, or publish a target repository; add credentials or automatic
approval; add provider routing; start browser, Docker, Unity, GPU, desktop, RPA,
MCP, or tunnel workers; expose a public service; deploy; release; or make a
production-readiness claim.
