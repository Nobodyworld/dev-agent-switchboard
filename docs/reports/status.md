# Public Developer Preview Status

_Last reviewed: 2026-08-15_

## Classification

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

The repository is public for source inspection, controlled local evaluation, and contribution. That does not authorize a production deployment, public hosted service, untrusted multi-tenant operation, or direct internet-facing use. Switchboard remains intended for localhost or controlled trusted networks.

## Published preview

The historical developer-preview checkpoint remains:

```text
tag: v0.1.0-preview.1
commit: dcac19fb211e105474cf74831a9cc53ef2138ea3
```

That tag predates later execution-broker product slices. It is not current `main`, a general-availability release, or production authorization.

## Current merged baseline

Current `main` is:

```text
eef4df6c43807576bf1c067200b44f16d6dd8e31
```

It includes:

- the task-coordination server, API, Python client, dashboard, observability, and Docker packaging;
- exact-SHA work orders, explicit approval, execution runs, leases, heartbeats, cancellation, and terminal completion;
- an outbound trusted local worker using operator-allowlisted repositories and disposable read-only exact-SHA worktrees;
- fixed reviewed argv, bounded/redacted output, full process-tree cancellation, ownership checks, and contained cleanup;
- compact evidence with dependency identity, parsed results, retained artifact hashes, deterministic fingerprints, and local-path rejection;
- exact GitHub pull-request resolution and explicit current/stale evidence publication;
- opt-in same-worker exact evidence reuse after retained local cryptographic proof;
- deterministic `first_available` and `cheapest_capable` routing using server-owned integer cost, quota, priority, capacity, and route provenance;
- the Validation Broker operator interface;
- a strict two-repository source-controlled workload catalog with `validate-accounting-modular@1`;
- repository-aware readiness, routing, exact reuse, and a dedicated Python 3.12 accounting acceptance gate;
- the dependency convergence from PR #144, including current framework/tooling versions, Ruff alignment, POSIX process-group lifecycle correction, and trusted Python interpreter binding.

PR #144 was squash-merged as the current baseline. Its merged-main CI run `31661847137` passed lint, typecheck, test, security, Secrets audit, Link check, Coverage, strict Browser UI tests, and Accounting workload acceptance.

## Active large slice

Issue #143 and draft PR #145 are the active large coherent product slice.

```text
starting main: eef4df6c43807576bf1c067200b44f16d6dd8e31
branch: feat/public-workload-onboarding-factory
pull request: #145 — draft, open, unmerged
ExecPlan: .agent/execplans/015_public_workload_onboarding_factory.md
state: connector planning and status initialization complete; local implementation not started
```

The slice will turn bespoke public workload onboarding into a repeatable source-controlled factory and prove it with:

- `validate-zscripts@1` for `Nobodyworld/dev-logger-zscripts`;
- `validate-industry-resilience@1` for `Nobodyworld/app-industry-resilience`.

The intended completed public catalog contains exactly:

1. `Nobodyworld/dev-agent-switchboard`;
2. `Nobodyworld/app-accounting-modular`;
3. `Nobodyworld/dev-logger-zscripts`;
4. `Nobodyworld/app-industry-resilience`.

The slice also adds deterministic catalog/profile validation, truthful pnpm capability matching, a bounded read-only catalog readiness overview, workload-pack history, committed synthetic fresh/reuse production-path acceptances, dedicated hosted acceptance jobs, documentation, and controlled live evidence or precise blockers.

## External target state

### Zscripts

```text
repository: Nobodyworld/dev-logger-zscripts
current reviewed main: c96628e2409dbb4d184030fc29fd431050b3009c
planned live target: PR #119
PR #119 state: closed and merged
live dogfood disposition: TARGET-STATE-BLOCKED
```

The profile must reproduce the current protected deterministic quality contract under Python 3.11, Node 24.12.0, and pnpm 10.18.1. No replacement PR may be substituted, and current-main inspection must not be represented as live exact-PR dogfood.

### Industry Resilience

```text
repository: Nobodyworld/app-industry-resilience
live target: PR #130
observed state: open, draft, mergeable
observed head: 5e458da35accc9fedd9f29a521de5c27b757a8d0
CI Quality Gate: 31553906171 — success
Docker Smoke: 31553906099 — success
```

The generic profile must translate the protected Makefile gate into fixed direct argv under Python 3.13. It must not require GNU Make or claim target Docker, Edge, Playwright, screen-reader, release, or publication acceptance. The exact PR state and head must be re-resolved immediately before implementation and live dogfood.

## Validation posture

The protected GitHub Actions matrix currently exercises:

- Commitlint;
- pinned pre-commit and repository-policy checks;
- Ruff and Black formatting validation;
- strict Mypy type checking;
- full pytest execution;
- configured aggregate and module coverage gates;
- Bandit and dependency auditing;
- full-history Gitleaks scanning;
- documentation link validation;
- strict browser UI tests that fail when skipped;
- dedicated Python 3.12 accounting workload acceptance.

Issue #143 must preserve every existing protected check and add isolated exact-result acceptance jobs for the new synthetic Zscripts and Industry Resilience profiles. External repositories must not be checked out or executed in hosted Switchboard CI.

## Security and execution boundary

The active slice does not authorize:

- arbitrary or runtime-authored commands;
- executable YAML, JSON, TOML, database, API, or target-repository profiles;
- caller-controlled argv, parsers, environment values, artifact paths, working directories, URLs, or cleanup targets;
- private repository metadata in the public catalog;
- target source writes;
- external PR comments or state changes;
- paid-provider execution or billing claims;
- MCP or Secure MCP Tunnel implementation;
- browser, Docker, Unity, GPU, desktop, or RPA worker expansion;
- release, publication, deployment, auto-merge, force-push, rebase, or history rewriting.

Workers remain outbound, read-only, exact-SHA, fixed-argv evidence producers. Full logs and artifact bytes remain local. GitHub and the owner retain repository and merge authority.

## Roadmap

The execution-broker roadmap is tracked in issue #111.

The current sequence is:

1. complete issue #143 through draft PR #145, local evidence, hosted evidence, controlled live dogfood or precise blockers, and final connector review;
2. merge only after a separate explicit expected-head owner authorization;
3. use the resulting workload factory to onboard further high-value deterministic profiles;
4. define a separate typed MCP/Secure MCP Tunnel architecture only after local-first profile utility is proven;
5. keep paid-provider handoff, browser workers, Docker workers, desktop/RPA, and write-capable workers behind separate accepted threat models and issues.

## Release and deployment boundary

Technical validation, public source visibility, and a developer-preview tag do not authorize production or public hosting. Any later tag, release, deployment, expanded network exposure, untrusted multi-tenant claim, paid-provider execution, or write-capable worker remains a separate owner-controlled decision with its own accepted contract and evidence.
