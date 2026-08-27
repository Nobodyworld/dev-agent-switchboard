# Public Developer Preview Status

_Last reviewed: 2026-08-27_

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
PR #147 head: 0019f0cc3675696e897d5d8ce267a7300847c631
Commitlint: 33048983337 success
CI: 33048983354 success
Workload acceptance: 33048983364 success
Connector review: 5038453077 — no blocking implementation defect; target-state blocker remains
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

### 2026-08-27 issue #146 acceptance disposition: target-state blocked

Three isolated attempts against immutable target
`a21aa33cabd143dbfefebe4ba32572ddb5765752` are retained as failed evidence:

1. The first attempt executed all seven reviewed steps and finalized local
   evidence, but completion returned HTTP `422` because serialized relative
   Windows backslashes matched the absolute-local-path policy.
2. The second attempt exposed combined-suite load behavior: three Windows
   cancellation cases exceeded their end-to-end four-second expectation and
   two server-backed smoke cases self-throttled with HTTP `429`. Those same
   nodes passed when isolated; the failed database and evidence remain
   unchanged.
3. The third attempt used a fresh isolated environment. Five deterministic
   steps passed, the exact target test step reported `696` passed, `12` skipped,
   and two failed server-smoke cases, and the required security step did not
   run. Completion then returned a bounded HTTP `422` diagnostic because compact
   stdout retained source text shaped like a local SQLite DSN. Its work order,
   run, lease, and capacity state remain unchanged for diagnosis.

The exact target is now **TARGET-STATE-BLOCKED**. Its two server-smoke tests use
`0.05`-second heartbeats beneath the default `120` requests per `60` seconds
limiter and can self-throttle when reached after preceding suite workload. The
production worker cadence remains caller-configured; the correction changes
only those two test fixtures to the existing realistic five-second server-smoke
cadence. Compact worker summaries now recursively replace local SQLite DSNs
with `[LOCAL_DATABASE_URI]`, while raw SQLite DSNs still fail server schema and
API validation. Typed HTTP diagnostics retain only bounded safe status, reason,
location, type, and sanitized message fields; they never retain raw response or
request content.

No fourth live acceptance and no `allow_exact` request ran, and no fourth run
against `a21aa33cabd143dbfefebe4ba32572ddb5765752` is authorized. There is no
authoritative successful fresh source run, reuse run, zero-step reuse proof, or
avoided-work claim. All three failed environments remain preserved. Exact-head
connector review `5038453077` found no blocking implementation defect, but the
target-state blocker remains. PR #147 remains draft and unmerged; the next step
is a separate owner target/merge decision. Focused or full local tests are not
substitutes for the missing live fresh/reuse evidence, and no release or
production authorization exists.

Correction validation passed `735` tests with `10` documented platform skips
both through the exact candidate command and an independent full-suite run.
Aggregate server coverage was `94%`; every configured module threshold passed,
and strict Playwright passed four cases with zero skips. Pinned Ruff and Bandit,
Mypy, scoped pre-commit, Gitleaks, detect-secrets, TOML/YAML, Node syntax,
full-SHA action pins, catalog, TODO, formatting, diff, and public-path hygiene
passed. All-files pre-commit was blocked by the local safety boundary, Lychee is
unavailable, and the shared-environment `pip-audit` result contained `117`
advisories across `29` packages rather than providing isolated project evidence.

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
planned live PR #130: closed and merged
reviewed head: e3fea89db624414fe3cad7980768f0265cf9570a
merge commit: f99abbf42c898f0fe4a7494f09b4aae13bed5c40
live dogfood disposition: TARGET-STATE-BLOCKED
```

The exact reviewed-head Quality Gate run `32536731040` and Docker Smoke run
`32536731320` succeeded. The generic profile is merged and synthetically proven,
but no substitute current-main execution may be represented as live exact-PR
dogfood. The earlier environment-isolation boundary also remains valid for any
future external-target campaign; green target checks do not remove it.

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

1. obtain a separate owner target/merge decision after completed exact-head
   connector review of PR #147, including selection of any newly authorized
   immutable target before later acceptance;
2. use the acceptance evidence to identify actual operator friction;
3. define scoped worker identity and an accepted isolation mode before exposing broader remote request surfaces;
4. define a separate typed MCP/Secure MCP Tunnel architecture only after local-first utility is proven;
5. keep paid-provider handoff, browser workers, Docker workers, Unity workers, desktop/RPA, and write-capable workers behind separate accepted issues and threat models.

## Release and deployment boundary

Technical validation, public source visibility, and a developer-preview tag do not authorize production or public hosting. A later tag, release, deployment, expanded network exposure, untrusted multi-tenant claim, paid-provider execution, or write-capable worker remains a separate owner-controlled decision with its own immutable candidate, accepted contract, and evidence.
