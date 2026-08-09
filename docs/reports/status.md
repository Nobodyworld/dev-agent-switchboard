# Public Developer Preview Status

_Last reviewed: 2026-08-08_

## Classification

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

The repository is public for source inspection, local evaluation, and contribution.
That does not authorize a formal release, public hosted service, untrusted
multi-tenant deployment, or direct internet-facing production use.

Switchboard is intended for localhost or controlled trusted networks.

## Current product baseline

The merged foundation includes:

- the task-coordination server, API, Python client, admin UI, and Docker packaging;
- a versioned execution control plane with explicit approval, work orders, workers,
  execution runs, leases, heartbeats, cancellation, and terminal completion;
- an outbound-only trusted local worker using operator-allowlisted repositories,
  exact-SHA disposable worktrees, immutable fixed argv, bounded output, retained
  local logs, ownership checks, cancellation, process-tree termination, and cleanup;
- the merged `validate-switchboard@1` workflow with strict compact evidence,
  worker-owned retained artifacts, dependency-lock hashes, parsed validation results,
  deterministic fingerprints, server-side local-path rejection, and the read-only
  `GET /api/execution/runs/{run_id}/evidence` endpoint;
- exact GitHub pull-request resolution and explicit current/stale compact-evidence
  publication;
- exact same-worker evidence reuse and deterministic cheapest-capable local routing
  with operator-owned cost/quota profiles.

Draft PR #137 adds the Validation Broker command center over that merged control
plane: bounded operator projections, policy-aware request identity, explicit
lifecycle controls, routing-profile management, fresh/reused history, and
database-derived avoided-work metrics. It remains draft and is not part of the
merged baseline until review and the protected matrix complete.

Connector review `4890406546` required final correction evidence before that
review can complete: a real `ExecutionClient`/`LocalWorker` fresh-then-reuse
acceptance, bounded rollback for unknown preferred workers, and complete
route/quota/source/timing plus worker-state visibility. The browser fixture
remains UI-only; it is not cited as cryptographic retained-evidence proof.

Operator setup, repository allowlisting, evidence retention, and trust limitations are
documented in the [local worker operations guide](../operations/local-worker.md).

The exact-SHA evidence work merged through issue
[#114](https://github.com/Nobodyworld/dev-agent-switchboard/issues/114) and pull
request [#120](https://github.com/Nobodyworld/dev-agent-switchboard/pull/120) at:

```text
dcb8e283f8445dd76f215a98023197d8ed5acab3
```

Consult those records and the living ExecPlan for the manifest digest, executed
validation, exact proof SHAs, and implementation limitations.

## Validation posture

The protected GitHub Actions matrix exercises:

- pinned pre-commit and repository policy checks;
- Ruff and Black formatting validation;
- strict Mypy type checking;
- full pytest execution;
- configured aggregate and module coverage gates;
- Bandit and dependency auditing;
- full-history Gitleaks scanning;
- documentation link validation;
- strict browser UI tests that fail when skipped.

Exact run identifiers, counts, coverage measurements, and environment limitations
belong in active pull requests, living ExecPlans, and the release audit. This page
intentionally avoids duplicating rapidly stale numeric evidence.

## Formal release remains blocked

The authoritative release tracker is issue
[#95](https://github.com/Nobodyworld/dev-agent-switchboard/issues/95). The
Linux, Docker, and clean-environment evidence handoff is issue
[#104](https://github.com/Nobodyworld/dev-agent-switchboard/issues/104).

No immutable release-candidate SHA has been selected yet. Issue #104 will record one
only after the release-scoped documentation decision is resolved.

Before a formal release, the project still requires:

1. one immutable release-candidate SHA;
2. the Linux symlink-containment regression to execute and pass without a skip;
3. complete clean-clone validation against that exact SHA;
4. a successful Docker build or a precise documented blocker;
5. final public-security and repository-setting review;
6. an updated `PUBLIC_RELEASE_AUDIT.md` containing executed evidence and explicit
   release authorization.

The merged evidence workflow is part of the current product baseline. Its merge did
not by itself authorize a release, production deployment, or public hosted service.

## Product roadmap

The execution-broker roadmap is tracked in issue
[#111](https://github.com/Nobodyworld/dev-agent-switchboard/issues/111).

Issue [#136](https://github.com/Nobodyworld/dev-agent-switchboard/issues/136)
tracks the current command-center product slice. Fresh execution remains the
default and explicit approval/publication remain mandatory. Do not infer that a
draft pull request is merged or release-authorized merely because its workflow is
documented.
