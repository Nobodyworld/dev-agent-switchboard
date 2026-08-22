# Public Developer Preview Status

_Last reviewed: 2026-08-21_

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
state: source publication authorized for existing draft PR review; live public-target dogfood, merge, release, and hosted-success claims remain blocked
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

The factory is reviewed source under `server/execution/workload_profiles.py`,
not an API, database, YAML, or target-repository profile surface. It compiles
typed fixed argv, capabilities, result-affecting inputs, result contracts,
artifact declarations, resource ceilings, and exclusions into the new manifests.
Legacy manifest identity inputs remain stable; the new source-controlled result
contract participates in new-manifest digest and exact-reuse identity. The
catalog-readiness API and Validation Broker expose only four-entry safe display
metadata, normalized runtimes, aggregate readiness, a public blocker, compact
latest outcome, exact-source caveat, and exclusions. They are non-mutating and
never expose target source paths, commands, logs, artifact bytes, credentials,
or private worker details.

Final local evidence on 2026-08-17 includes deterministic offline catalog
validation, the exact three legacy digest checks, source-profile validation
coverage of 240/240 selected lines, serial Python 3.11 pytest (`682` passed,
`16` known platform/fixture skips), strict Playwright (`4` passed, zero skips),
and one passing synthetic production-path acceptance each for Accounting
(Python 3.12), Zscripts (Python 3.11), and Industry Resilience (Python 3.13).
Windows and WSL/Linux runner stress also passed their required cancellation and
full-module repetitions. These are local/synthetic proofs, not live external
dogfood or release approval.

The final publication audit on 2026-08-21 passed the offline catalog validator,
TODO policy, repository-wide diff check, all-files pre-commit, Node syntax,
full action-SHA pin validation, 43 focused profile/catalog/pnpm/capability
tests, and 16 native containment/finalization tests with three explicitly
Linux-only skips. The single bounded `pip-audit` attempt produced no response
and was stopped after 60 seconds; Docker is unavailable locally. The single
`git fsck --full` attempt was environment-blocked by sandbox permission errors
reading the shared object store. None of those three unavailable checks is
claimed as passed.

PR #145's current body and issue #143's latest coordination comment are the
authoritative external-target dispositions for this slice. The exact states
below were independently re-resolved read-only from GitHub on 2026-08-21.

## External target state

### Zscripts

```text
repository: Nobodyworld/dev-logger-zscripts
current reviewed main: c96628e2409dbb4d184030fc29fd431050b3009c
planned live target: PR #119
PR #119 state: closed and merged
PR #119 merged head: 5fbb3a219d04ea3631042ef3a98272e1b5fca579
final read-only re-resolution: 2026-08-21T22:10:14Z
live dogfood disposition: TARGET-STATE-BLOCKED
```

The profile must reproduce the current protected deterministic quality contract under Python 3.11, Node 24.12.0, and pnpm 10.18.1. No replacement PR may be substituted, and current-main inspection must not be represented as live exact-PR dogfood.

### Industry Resilience

```text
repository: Nobodyworld/app-industry-resilience
live target: PR #130
observed state: open, draft, mergeable
observed head: e3fea89db624414fe3cad7980768f0265cf9570a
CI: 32536731040 — success
Docker Smoke: 32536731320 — success
final read-only re-resolution: 2026-08-22T00:56:48Z
live dogfood disposition: ENVIRONMENT-BLOCKED
```

The former `5e458da35accc9fedd9f29a521de5c27b757a8d0` and
`01c4ebf52fcae3cce8771371228723db772d1459` observations are historical. The
current head is six commits beyond the former and three beyond the latter. The
latest three commits change Streamlit configuration/UI, public API/pipeline
behavior, tests, and documentation. GitHub content metadata confirms identical
blob IDs across both target movements for `Makefile`,
`.github/workflows/ci.yml`, `requirements.txt`, `requirements-dev.txt`,
`config/.secrets.baseline`, and `src/scripts/benchmark_metrics.py`, so the
reviewed deterministic profile contract has not moved.

The generic profile translates the protected Makefile gate into ten fixed direct
argv steps under Python 3.13: Python version, `pip check`, Black, Ruff, Mypy,
required eight-module runtime coverage at 85%, informational full-source
coverage, benchmark metrics, one combined pip-audit JSON report, and
baseline-only `detect_secrets.pre_commit_hook`. It does not require GNU Make,
and the detect-secrets step is not a source secret scan. It must not claim
target Docker, Edge, Playwright, screen-reader, release, or publication
acceptance. The exact PR state and head must be re-resolved immediately before
live dogfood.

There is no operator-approved canonical Industry checkout in this campaign, and
the available worker does not provide a separate least-privilege OS identity
plus a container/VM or equivalent ACL/mount boundary. These are explicit
live-dogfood blockers: no clone, fetch, external worktree, source execution,
PR comment, or live-evidence claim is authorized until an operator supplies
both an exact canonical checkout and that isolation boundary.

No controlled live execution was attempted during the 2026-08-21 re-resolution.
Green exact-head target checks do not remove the checkout or isolation blockers,
and this slice does not authorize building a new container, VM, ACL, account, or
Docker-worker architecture merely to eliminate them.

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
- dedicated Python 3.12 accounting workload acceptance;
- draft-only isolated Zscripts and Industry Resilience synthetic real-worker
  acceptance jobs, each guarded as exactly one passing JUnit case with no skip,
  failure, or error; they do not check out or execute external targets.

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

Workers remain outbound, exact-SHA, fixed-argv evidence producers. The
reviewed `read_only` policy is cooperative trust plus integrity detection, not
an operating-system sandbox: a same-account public target must not share the
worker's control-plane bearer token, canonical source, publication credentials,
or mutable Git state. Full logs and artifact bytes remain local. GitHub and the
owner retain repository and merge authority.

The strict factory-profile host adds bounded ordinary-process containment (a
Windows Job Object or Linux subreaper) and drains a worker when quiescence is
unproven. It does not establish the required public-target isolation boundary;
in particular, same-identity state and a Linux parentage escape remain outside
that host-level defense. Source publication to the existing draft PR is for
connector review only; it is not live-dogfood, production, merge, or release
readiness.

To revoke an onboarded workload, make and deploy a separate reviewed
source-controlled catalog/profile change, then remove or stop relevant worker
mappings. This blocks future routing without changing historical manifests,
evidence identities, retained evidence, or prior publication records. A
rollback restores a previously reviewed source revision and requires renewed
catalog/capability validation; it never creates target-source write authority.

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
