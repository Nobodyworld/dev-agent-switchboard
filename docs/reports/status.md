# Public Developer Preview Status

_Last reviewed: 2026-08-11_

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
83f84a7ee07b4f5cdddfa7611242a529897fa842
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

## Current draft slice

Draft PR #139 now contains a strict two-repository source-controlled catalog,
explicit repository-to-manifest compatibility, bounded logical worker
availability, restart-safe Switchboard-only legacy defaults, repository-aware
routing/reuse, catalog-driven command-center onboarding, and the external
`validate-accounting-modular@1` fixed contract. Existing Switchboard manifest
digests remain unchanged.

The file-backed production-path acceptance uses real FastAPI execution/GitHub
routes, `ExecutionClient`, `LocalWorker`, worker-owned evidence storage, and a
mocked GitHub transport. It proves an unmapped cheaper worker cannot claim the
accounting request, all eleven trusted steps run freshly on the mapped worker,
declared coverage/log/result/ownership evidence is retained, and the second
same-identity request reuses after worker-local verification with zero executed
steps. The canonical Git repository remains clean.

The draft follow-up makes repository readiness request-aware and routes it
through the same pure evaluator as assessment and checkout. It catches the
accounting Python 3.11 mismatch, permits profile-free first-available workers,
enforces profile/cost/quota only for cheapest-capable, keeps hard pins strict,
and performs no readiness writes. Broad quality and coverage return to Python
3.11; the exact real accounting acceptance runs alone in a required Python 3.12
job that fails on skips or any result other than one passing test.

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

Target state changed after planning: PR #126 merged before implementation could
perform truthful current-PR dogfood. Its final head is
`a7af5766a4e83a95c64a40bfdc606ee7b280cbf5` and merge commit is
`4266ea43ed40201388df82bb53f757df45afe204`. No target mutation or publication
was attempted, and synthetic real-worker evidence is not represented as live
target-PR dogfood.

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

1. complete review and hosted validation of issue #138 / draft PR #139 while retaining the merged-target blocker truthfully;
2. onboard additional deterministic workloads only through reviewed fixed profiles;
3. define a separate typed MCP/Secure MCP Tunnel architecture after local-first utility is proven;
4. keep paid-provider handoff behind local profile coverage and truthful evidence;
5. treat browser, desktop, Unity, Docker, and RPA workers as later specialized capability slices.
