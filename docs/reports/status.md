# Public Developer Preview Status

_Last reviewed: 2026-08-09_

## Classification

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

The repository is public for source inspection, controlled local evaluation, and contribution. That does not authorize a production deployment, public hosted service, untrusted multi-tenant operation, or direct internet-facing use. Switchboard remains intended for localhost or controlled trusted networks.

## Published preview

The developer-preview checkpoint is:

```text
tag: v0.1.0-preview.1
commit: dcac19fb211e105474cf74831a9cc53ef2138ea3
```

That preview predates later execution-broker product slices. It is a historical public checkpoint, not the current `main` and not a production release.

## Current merged baseline

Current `main` is:

```text
33a5836496fa933dd6aae65ec71238d1b5ac9772
```

The merged baseline includes:

- the task-coordination server, API, Python client, dashboard, observability, and Docker packaging;
- an exact-SHA execution control plane with explicit approval, work orders, workers, runs, leases, heartbeats, cancellation, and terminal completion;
- an outbound trusted local worker using operator-allowlisted repositories, disposable read-only exact-SHA worktrees, fixed reviewed argv, bounded/redacted output, retained local logs, ownership checks, cancellation, process-tree termination, and contained cleanup;
- compact validation evidence with dependency-lock identity, parsed test/coverage/security results, retained artifact hashes, deterministic fingerprints, and local-path rejection;
- exact GitHub pull-request resolution and explicit managed current/stale evidence publication;
- opt-in same-worker exact evidence reuse after retained local cryptographic proof;
- deterministic `first_available` and `cheapest_capable` local routing with operator-owned integer cost, quota, priority, active-poll, capacity, and route provenance;
- the merged Validation Broker command center for worker/profile setup, exact-PR requests, explicit approval and queueing, fresh or reused execution, explicit publication, bounded history, and truthful avoided-work metrics.

The Validation Broker merged through issue #136 and PR #137. Its exact accepted head was `ba9d0a8184448a1ae0c30357a18a7b5962dea94d`, squash-merged as the current baseline above. Full local and hosted evidence remains in the PR, issue, and living ExecPlan.

## Current limitation

The version-controlled execution registry still trusts only `Nobodyworld/dev-agent-switchboard`. Local worker configuration can map more than one logical repository, but the server does not yet expose bounded repository availability, enforce repository-to-manifest compatibility, or prevent assignment to a worker that lacks a target repository before checkout.

That means the command center is operational but still largely self-validating. The active slice must prove practical value against a real approved external workload before MCP, paid-provider handoff, browser-worker, or desktop/RPA expansion.

## Active large slice

Issue [#138](https://github.com/Nobodyworld/dev-agent-switchboard/issues/138) and draft PR [#139](https://github.com/Nobodyworld/dev-agent-switchboard/pull/139) implement:

- a strict source-controlled trusted repository/workload catalog;
- explicit repository-to-manifest compatibility;
- preserved existing Switchboard manifest identities and digests;
- first external `validate-accounting-modular@1` manifest;
- bounded worker logical repository availability without local paths;
- restart-safe persistence compatibility;
- repository-aware routing, hard pins, assessment, and exact reuse;
- repository-aware command-center onboarding and readiness;
- controlled real fresh-then-reused dogfood against the exact current head of public `Nobodyworld/app-accounting-modular` PR #126, or a precise environment blocker.

The target PR must not be modified, published to, merged, closed, retargeted, or marked ready automatically. Approval and publication remain explicit.

## Validation posture

The protected GitHub Actions matrix exercises:

- Commitlint;
- pinned pre-commit and repository-policy checks;
- Ruff and Black formatting validation;
- strict Mypy type checking;
- full pytest execution;
- configured aggregate and module coverage gates;
- Bandit and dependency auditing;
- full-history Gitleaks scanning;
- documentation link validation;
- strict browser UI tests that fail when skipped.

Exact workflow identifiers, test counts, coverage measurements, target dogfood SHA, and environment limitations belong in active pull requests and living ExecPlans. This page intentionally records durable capability and scope rather than rapidly stale run details.

## Release and deployment boundary

Technical validation, a public repository, and a developer-preview tag do not authorize production or public hosting. Any later tag, release, deployment, expanded network exposure, untrusted multi-tenant claim, paid-provider execution, or write-capable worker remains a separate owner-controlled decision with its own accepted contract and evidence.

## Roadmap

The execution-broker roadmap is tracked in issue [#111](https://github.com/Nobodyworld/dev-agent-switchboard/issues/111).

The current sequence is:

1. complete trusted multi-repository onboarding and real external local dogfood in issue #138 / PR #139;
2. onboard additional deterministic workloads only through reviewed fixed profiles;
3. define a separate typed MCP/Secure MCP Tunnel architecture after local-first utility is proven;
4. keep paid-provider handoff behind local profile coverage and truthful evidence;
5. treat browser, desktop, Unity, Docker, and RPA workers as later specialized capability slices.
