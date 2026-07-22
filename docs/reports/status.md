# Public Developer Preview Status

_Last reviewed: 2026-07-22_

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
  local logs, ownership checks, cancellation, process-tree termination, and cleanup.

The exact-SHA compact-evidence workflow is tracked by issue
[#114](https://github.com/Nobodyworld/dev-agent-switchboard/issues/114) and pull
request [#120](https://github.com/Nobodyworld/dev-agent-switchboard/pull/120).
Consult those records rather than this page for its current merge state, tested
head SHA, manifest digest, and validation evidence.

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
belong in the active pull request, living ExecPlan, and release audit. This page
intentionally avoids duplicating rapidly stale numeric evidence.

## Formal release remains blocked

The authoritative release tracker is issue
[#95](https://github.com/Nobodyworld/dev-agent-switchboard/issues/95). The
Linux, Docker, and clean-environment evidence handoff is issue
[#104](https://github.com/Nobodyworld/dev-agent-switchboard/issues/104).

Before a formal release, the project still requires:

1. an explicit owner decision on release scope;
2. one immutable release-candidate SHA;
3. the Linux symlink-containment regression to execute and pass without a skip;
4. complete clean-clone validation against that exact SHA;
5. a successful Docker build or a precise documented blocker;
6. final public-security and repository-setting review;
7. an updated `PUBLIC_RELEASE_AUDIT.md` containing executed evidence and explicit
   release authorization.

## Product roadmap

The execution-broker roadmap is tracked in issue
[#111](https://github.com/Nobodyworld/dev-agent-switchboard/issues/111).

The next bounded slices are:

- [#121](https://github.com/Nobodyworld/dev-agent-switchboard/issues/121) — exact
  evidence reuse with worker-local availability proof;
- [#122](https://github.com/Nobodyworld/dev-agent-switchboard/issues/122) — resolve
  an exact GitHub pull-request head and publish compact validation evidence.

Do not infer that roadmap work is merged or release-authorized merely because an
issue has been specified.
