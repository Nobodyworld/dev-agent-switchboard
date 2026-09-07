# Operator validation: report and input boundaries

> **PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY**

This supplements [Operator validation lifecycle](operator-validation-lifecycle.md)
for issue #151 / PR #152. It does not authorize new targets, execution modes,
credentials, source writes, publication, or historical-runtime cleanup.

## Reports are complete recorded contracts

Both report serializers validate schema version 2, exact primitive types, bounded
collections, every run, and the whole lifecycle. Boolean values are not integer
counters. Stored JSON must contain the complete known field set; absent fields
are not filled with defaults and unknown fields are rejected.

A successful report requires the complete ordered phase sequence, the appropriate
one or two verified runs, explicit approvals, exact action counts, successful
source/process/port cleanup, zero active leases and worker capacity, and a valid
completion timestamp. Exact reuse additionally requires distinct work-order and
run IDs, the original source-run linkage, the same worker and result identity,
unchanged retention expiry, zero repeated steps/artifacts, and the exact avoided
step count. An empty or internally contradictory success report is rejected.

Partial failures remain reportable. An approval action whose API acknowledgement
failed is not represented as an acknowledged approval. No failed report is
upgraded to success merely because child processes stopped successfully.

## Inspection is not live revalidation

`inspect-validation-runtime` reads the original ownership marker and optional
report. Report reads use the same stable, bounded, regular-file/no-follow reader
as runtime records. Ownership and report-parent ancestry are checked before and
after reading. Linked or reparse report parents, file links, marker replacement,
unstable records, malformed JSON, duplicate keys, non-finite JSON constants,
non-object reports, and oversized reports fail closed. A present invalid report
is not treated as an absent report.

Human inspection output begins with:

```text
inspection: stored state only; live evidence not reverified
```

The returned JSON remains the recorded schema-2 snapshot, not a new execution
result. Inspection does not query running processes or the database, rehash
artifacts, check current source state, renew retention, authenticate the report's
historical authorship, or authorize reuse. Retention consistency is checked
against the recorded completion time, not the date of inspection. A coherent
historical report can therefore remain readable after its evidence expires.

Inspection never rewrites, migrates, repairs, deletes, or fabricates a historical
report. Rejected files remain available for private diagnosis. Normal filesystem
access-time handling belongs to the operating system; the command does not write
or adjust recorded timestamps.

## Timeout compatibility is a preflight requirement

The operator's execution budget becomes the generated worker's overall and
maximum-step limits. Before creating a runtime, preflight rejects a manifest or
step exceeding those limits, and rejects a terminal-observation budget shorter
than the selected manifest budget. Rejection returns a bounded reason:

```text
manifest_timeout_exceeds_worker_budget
manifest_step_timeout_exceeds_worker_budget
terminal_timeout_below_manifest_budget
```

The default execution budget is 3,600 seconds. The existing Accounting manifest
requires 5,400 seconds, so selecting it with the default budget is rejected before
launch. Deliberate private configuration can specify, for example:

```json
{
  "work_order_timeout_seconds": 5400,
  "terminal_timeout_seconds": 6000
}
```

These are fields to add to an otherwise complete operator configuration, not a
standalone configuration. No timeout is increased silently. Passing this check
is not approval to execute an external repository and does not replace its other
source, toolchain, isolation, or authorization requirements.

## Configuration and loopback origins

Configuration reads consume at most 64 KiB plus one overflow-detection byte.
Duplicate keys are rejected at every JSON object level. NaN and infinity are
rejected; schema version must be an integer rather than a Boolean, float, or
string. Failure messages do not echo duplicate values or private paths.

The lifecycle client and generated worker configuration use the same loopback
origin builder. IPv6 host `::1` produces `http://[::1]:8765`, while IPv4 and
`localhost` retain their existing forms. Socket host arguments remain unbracketed.
The synthetic server/worker acceptance covers both supported lifecycle modes on
IPv4 and IPv6; an IPv6 case may skip only when its loopback socket cannot bind.

## Verification scope

The focused regressions are in
`client/python/tests/test_execution_operator_corrections.py` and the existing
`client/python/tests/test_execution_operator.py`. They cover false-success
rejection, legitimate partial failure, strict JSON input, report preservation,
symlink/junction and marker replacement boundaries, Accounting timeout preflight,
and both URL consumers. Hosted synthetic acceptance is not live-target dogfood.

See the [ExecPlan 018 correction addendum](../../.agent/execplans/018_operator_validation_lifecycle_corrections.md)
for validation and preservation requirements. Current PR-head checks and explicit
local evidence, not a previous head's green status, determine readiness.
