# Public Developer Preview Status

_Last reviewed: 2026-08-24_

## Classification

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

The repository is public for source inspection, controlled local evaluation, and contribution. This does not authorize production deployment, a public hosted service, direct internet exposure, or untrusted multi-tenant operation. Switchboard remains intended for localhost or controlled trusted networks.

## Current canonical state

```text
repository: Nobodyworld/dev-agent-switchboard
current merged main: a21aa33cabd143dbfefebe4ba32572ddb5765752
source: squash merge of PR #145
completed issue: #143
active issue: #146
active draft PR: #147
active branch: test/merged-workload-factory-acceptance
active ExecPlan: .agent/execplans/016_merged_workload_factory_acceptance.md
```

PR #145 merged the public workload onboarding factory after exact-head local validation, hosted validation, and connector review. The merge retained the repository’s developer-preview classification and did not authorize release, deployment, live external target execution, MCP, paid-provider routing, or expanded worker types.

## Current merged product capability

Switchboard is a trusted local execution and evidence broker for AI-assisted development. It provides:

- dependency-aware task coordination, leases, heartbeats, and live plan/file updates;
- exact-SHA work orders and explicit approval;
- outbound local workers using immutable reviewed manifests and fixed shell-free argv;
- disposable exact-SHA worktrees with canonical-source integrity checks;
- bounded/redacted remote evidence with full local logs and retained artifact hashes;
- full process-tree cancellation, ownership checks, cleanup, and evidence retention;
- authenticated GitHub exact-PR resolution and explicit current/stale publication;
- same-worker exact evidence reuse after retained local cryptographic proof;
- deterministic `first_available` and `cheapest_capable` local routing;
- operator-visible route, quota, capacity, evidence, and history projections;
- the Validation Broker browser workspace;
- a strict source-controlled four-repository workload catalog;
- `validate-switchboard@1`;
- `validate-accounting-modular@1`;
- `validate-zscripts@1`;
- `validate-industry-resilience@1`;
- deterministic offline `python scripts/dev.py validate-workload-catalog` validation;
- isolated hosted synthetic acceptances for the external workload profiles.

Trusted workload profiles are reviewed Python source under `server/execution/workload_profiles.py`. Runtime YAML, JSON, TOML, database rows, API payloads, target metadata, or caller-provided values cannot author executable commands.

## Latest merged validation evidence

The exact PR #145 head was:

```text
aa4d236ae3c8d54ead03d00fcaf920d26b18f374
```

It passed:

```text
Commitlint          32735060831  success
Workload acceptance 32735060770  success
Main CI             32735060715  success
```

Main CI included:

- lint, all-files pre-commit, and TODO policy;
- strict Mypy;
- Bandit and hosted pip-audit;
- full-history Gitleaks;
- Lychee link validation;
- Accounting Python 3.12 acceptance;
- the complete Python 3.11 suite with exact Node 24.12.0 and pnpm 10.18.1 setup;
- strict Chromium UI tests with zero skips;
- aggregate coverage at 91%;
- all configured module thresholds.

The isolated workload workflow passed Zscripts, Industry Resilience, and focused workload-factory coverage. The resulting signed squash commit has the same source tree as the exact validated PR head.

The connector’s commit-associated workflow lookup currently filters to pull-request-triggered runs, so it cannot enumerate ordinary `main` push runs for the squash commit. This document therefore does not claim separate merged-main push-run identifiers.

## Active acceptance and reconciliation slice

Issue #146 / draft PR #147 must prove one real operator-controlled run against merged Switchboard itself:

```text
repository: Nobodyworld/dev-agent-switchboard
commit: a21aa33cabd143dbfefebe4ba32572ddb5765752
manifest: validate-switchboard@1
```

The slice must execute:

1. one explicitly approved fresh run through the real FastAPI server, outbound worker, routing, leases, worktree, runner, evidence, and cleanup path;
2. one distinct equivalent `allow_exact` request on the same worker;
3. retained-evidence verification with zero repeated deterministic validation steps;
4. exact source, route, evidence, artifact, integrity, and cleanup verification;
5. operator-friction and duration recording;
6. reconciliation of project authority and historical documentation;
7. safe disposition of stale local merged worktrees and branch names without losing stashes or unpublished work.

This slice adds no new execution architecture unless a real acceptance defect requires a narrow correction with regression coverage.

## External target state

### Zscripts

```text
repository: Nobodyworld/dev-logger-zscripts
planned live PR #119: closed and merged
live dogfood disposition: TARGET-STATE-BLOCKED
```

No substitute PR is authorized. Synthetic acceptance remains valid, but current-main execution must not be represented as exact live PR #119 evidence.

### Industry Resilience

```text
repository: Nobodyworld/app-industry-resilience
planned live PR #130: previously observed open, draft, mergeable
live dogfood disposition: ENVIRONMENT-BLOCKED
```

The generic profile is merged and synthetically proven. Live execution remains blocked until the operator supplies an exact canonical checkout and a separate least-privilege isolation boundary. Green target CI does not remove those preconditions.

## Security and execution boundary

Switchboard does not authorize:

- arbitrary or runtime-authored commands;
- caller-controlled argv, executable paths, working directories, parsers, artifact paths, environment values, URLs, or cleanup targets;
- private repository metadata in the public catalog;
- target source writes;
- external PR comments or state changes from deterministic workers;
- paid-provider execution or billing claims;
- MCP or Secure MCP Tunnel implementation without a separate accepted contract;
- browser, Docker, Unity, GPU, desktop, or RPA worker expansion without separate threat models;
- release, publication, deployment, auto-merge, force-push, rebase, or history rewriting.

`repository_write_policy=read_only` is cooperative trust plus integrity detection, not an operating-system sandbox. Untrusted target code requires a separate least-privilege identity and an accepted container, VM, ACL, mount, or equivalent isolation boundary.

## Published preview

The historical developer-preview checkpoint remains:

```text
tag: v0.1.0-preview.1
commit: dcac19fb211e105474cf74831a9cc53ef2138ea3
```

That tag predates exact evidence reuse, cost-aware routing, the Validation Broker, the multi-repository catalog, and the workload factory. It is a historical public checkpoint, not current `main`, a general-availability release, or production authorization.

Any later preview or formal release requires a new immutable candidate and separate owner authorization.

## Roadmap boundary

The execution-broker roadmap is tracked in issue #111.

The current sequence is:

1. complete issue #146 through real merged-product fresh/reuse acceptance and truth reconciliation;
2. use the acceptance evidence to identify actual operator friction;
3. define scoped worker identity and an accepted isolation mode before exposing broader remote request surfaces;
4. define a separate typed MCP/Secure MCP Tunnel architecture only after local-first utility is proven;
5. keep paid-provider handoff, browser workers, Docker workers, Unity workers, desktop/RPA, and write-capable workers behind separate accepted issues and threat models.

## Release and deployment boundary

Technical validation, public source visibility, and a developer-preview tag do not authorize production or public hosting. A later tag, release, deployment, expanded network exposure, untrusted multi-tenant claim, paid-provider execution, or write-capable worker remains a separate owner-controlled decision with its own immutable candidate, accepted contract, and evidence.
