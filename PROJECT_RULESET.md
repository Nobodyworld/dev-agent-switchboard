# Project Ruleset

## 1. Document control

| Field | Value |
|---|---|
| Project | Switchboard / `Nobodyworld/dev-agent-switchboard` |
| Filename | `PROJECT_RULESET.md` |
| Ruleset version | `1.0.0` |
| Status | Authoritative after merge |
| Classification | `PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY` |

This file governs project-specific planning, implementation, review, validation, GitHub operations, local execution, agent handoffs, and publication decisions for Switchboard. It does not override higher-level platform, legal, security, or safety requirements.

This file contains **stable operating rules only**. Current SHAs, active issues, active PRs, workflow IDs, test counts, coverage values, environment blockers, and current next actions belong in:

- `docs/reports/status.md`;
- current GitHub issues and pull requests;
- living ExecPlans under `.agent/execplans/`;
- dated release or validation audits.

## 2. Project identity

Switchboard is a public reference implementation for coordinating agents and deterministic local workers against shared dependency-aware work. It combines:

- task dependency management;
- lease and heartbeat ownership;
- live-file and plan synchronization;
- an operator dashboard;
- a separate trusted execution plane;
- outbound local workers;
- exact-commit validation;
- compact fingerprinted execution evidence;
- GitHub pull-request integration;
- opt-in exact evidence reuse;
- cost-aware routing among trusted local workers;
- source-controlled workload profiles.

Its primary purpose is to offload deterministic validation and approved local automation before consuming coding-agent capacity. Switchboard produces trustworthy evidence; it does not grant a model unrestricted control over a computer.

The governing execution unit is:

```text
exact repository + exact commit SHA + approved manifest/profile + expected evidence
```

## 3. Authoritative sources and precedence

When project sources conflict, use this order:

1. The owner’s newest explicit instruction.
2. Current Project instructions.
3. Current authoritative repository rules and security files.
4. The accepted current GitHub issue contract.
5. The living ExecPlan for the active branch.
6. The active PR body and current review decisions.
7. Older established conventions.
8. Reasonable inference, clearly labeled as provisional.

Interpretation rules:

- Merged source is stronger evidence of current behavior than older planning text.
- A current accepted issue governs its work slice unless the owner changes it.
- A living ExecPlan governs execution details for its branch.
- Historical audits describe only the immutable candidate they name.
- Moving facts must be reverified rather than copied from older records.
- Public summaries must not convert dated evidence into permanent claims.

## 4. Non-negotiable rules

### `RULE-001` — Owner control

Product behavior, scope, architecture, UX, security posture, release status, and acceptance criteria remain owner-controlled.

Narrow corrections already required by an accepted issue, review finding, or validation contract may proceed when they do not change product behavior.

### `RULE-002` — Connector first

Use the GitHub connector first for every supported remote operation, including repository inspection, issue and PR coordination, branch preparation, repository text edits, review, Actions inspection, comments, labels, and guarded merges.

Use local tools only for capabilities the connector cannot provide, such as terminal execution, local Git, dependency installation, tests, builds, runtime behavior, generated files, or unpushed state.

### `RULE-003` — Reserve coding agents for genuine coding or local execution

Use Codex or another coding agent only when work requires one or more of:

- local checkout access;
- coordinated multi-file implementation;
- dependency installation;
- tests, builds, scans, or runtime reproduction;
- non-obvious debugging;
- generated lockfiles;
- browser, desktop, Docker, Unity, or platform-specific validation;
- inspection or preservation of unpushed local work.

Deterministic execution should progressively move into reviewed Switchboard profiles.

### `RULE-004` — GitHub is canonical

GitHub is the source of truth for reviewed source, branches, issues, pull requests, merge decisions, and release checkpoints.

A preserved unpushed local worktree may be the temporary continuation source until safely reviewed and pushed.

### `RULE-005` — Exact commit identity

Authoritative deterministic execution requires an allowlisted repository and a full 40-character commit SHA.

A GitHub adapter may receive a PR number initially, but must resolve and persist the exact current PR-head SHA before normal work-order creation.

### `RULE-006` — No arbitrary remote shell

Models, connectors, API callers, and work orders must not supply arbitrary shell commands, executable paths, script bodies, caller-selected argv, working directories, cleanup targets, or filesystem paths for local execution.

### `RULE-007` — Immutable trusted manifests only

Workers execute only reviewed versioned manifests whose fixed argv and result-affecting definitions are controlled by trusted source and bound into an immutable digest.

Remote callers select a manifest and bounded inputs; they do not construct commands.

### `RULE-008` — Outbound-only workers

Local workers initiate communication by polling Switchboard. They do not expose a general inbound workstation-control listener.

A future secure relay or MCP tunnel may transport typed requests while preserving this outbound execution contract; it must not become a general proxy.

### `RULE-009` — Deny by default

Execution fails closed unless all required approval, repository, SHA, manifest, capability, worker-health, capacity, network, read-only, quota, lease, retention, route, and evidence conditions are satisfied.

Workers must not improvise around mismatches.

### `RULE-010` — Deterministic workers do not edit source

Deterministic workers must not stage, commit, push, merge, rebase, resolve conflicts, modify canonical source, open PRs, or automatically fix code.

A write-capable worker requires a separate owner-approved issue, approval tier, and threat model.

### `RULE-011` — Full execution data stays local

Full stdout, stderr, logs, artifact bytes, screenshots, environment details, and local filesystem paths remain in worker-owned local storage unless the owner explicitly approves a bounded typed transfer.

### `RULE-012` — Compact redacted evidence only

Normal APIs, GitHub comments, PR reports, and model-facing results expose only bounded redacted evidence.

They must not expose secrets, credentials, environment dumps, absolute local paths, machine identity, full capability documents, commands, argv, or unbounded logs.

### `RULE-013` — Material changes use branches and PRs

Material source, documentation, workflow, configuration, migration, and security changes use an isolated branch and pull request.

Direct `main` changes are not the default.

### `RULE-014` — Explicit merge authorization

A pull request remains unmerged until the owner explicitly authorizes merge.

Passing tests and connector review do not substitute for owner authorization.

### `RULE-015` — Guarded squash merge

Authorized merges use squash merge and the exact expected PR-head SHA. Abort if the head, checks, review state, or mergeability differs.

Auto-merge remains disabled unless the owner explicitly changes policy.

### `RULE-016` — No history rewriting by default

Do not force-push, rebase shared work, reset active branches, recreate active branches, or rewrite history without explicit owner authorization.

### `RULE-017` — Preserve interrupted local work

Preserve uncommitted, unpushed, partially validated, or otherwise uncertain worktrees exactly until inspected.

Do not reset, clean, stash, overwrite, or start a parallel replacement implementation merely because continuation is difficult.

### `RULE-018` — Never overstate evidence

Do not claim a test, build, scan, CI gate, manual check, merge, deployment, cleanup, or release passed unless available evidence proves it.

Use truthful statuses such as `pass`, `fail`, `environment-blocked`, `needs-review`, `unverified`, `stale`, and `partial`.

### `RULE-019` — Preserve developer-preview boundaries

Public material must use:

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

Public source visibility does not authorize production, direct public-internet exposure, untrusted multi-tenant operation, general availability, deployment, or unrestricted local control.

### `RULE-020` — Cost units are abstract

Routing cost units and avoided-work counts are operator-defined comparison values. They are not actual money, provider credits, tokens, bills, or measured financial savings.

### `RULE-021` — Prefer large coherent slices

Implementation normally uses large coherent product slices with locked scope, one canonical branch, one PR, one living ExecPlan, explicit exclusions, and a complete validation plan.

Security fixes, review corrections, migration fixes, and isolated documentation corrections should remain narrow.

### `RULE-022` — Handoffs contain no model recommendation

Codex handoffs must not recommend a model, model family, or reasoning-effort setting unless the owner requests that advice in the same turn.

### `RULE-023` — Stable rules and mutable status stay separate

Do not place current SHAs, active branch/PR state, workflow IDs, transient blockers, or test counts in this stable ruleset.

Keep them in current status, issues, PRs, ExecPlans, and dated audits.

### `RULE-024` — External dogfood is read-only

External workload dogfood must not modify external source, commits, branches, PRs, labels, comments, reviews, or publication state.

Green external CI does not itself satisfy local checkout, identity, isolation, or approval preconditions.

### `RULE-025` — Cooperative read-only policy is not a sandbox

`repository_write_policy=read_only` is reviewed policy plus integrity detection. It is not operating-system isolation.

Untrusted or insufficiently trusted target code requires a separate least-privilege identity and an accepted container, VM, ACL, mount, or equivalent boundary.

## 5. Scope and product boundaries

### In scope

- product planning and acceptance criteria;
- task coordination;
- exact-SHA work orders;
- immutable command manifests;
- outbound local-worker execution;
- compact evidence and local retention;
- exact evidence reuse;
- GitHub exact-PR resolution and bounded publication;
- local routing, capacity, and quota state;
- operator workflows and history;
- source-controlled workload onboarding;
- deterministic tests, builds, scans, packaging, diagnostics, and release evidence;
- connector-first GitHub coordination;
- coding-agent handoffs when local implementation is required.

### Current boundaries

- Switchboard is not a general remote shell.
- Switchboard is not an unrestricted autonomous coding system.
- Deterministic workers do not edit source.
- Full logs and artifact bytes stay local.
- Worker communication is outbound pull.
- Work is tied to exact source revisions.
- Approval remains explicit unless a later accepted policy says otherwise.
- GitHub remains canonical.
- Current cost routing is local-worker routing only.
- Public preview does not imply production safety.

### Out of scope without a new accepted issue

- arbitrary model-supplied shell execution;
- unrestricted file or network access;
- automatic source-code fixes by deterministic workers;
- automatic commits, pushes, PRs, approvals, or merges;
- paid coding-agent execution or provider credentials;
- production deployment;
- public-hosted multi-tenant operation;
- direct workstation inbound listeners;
- unrestricted RPA or desktop control;
- general artifact-byte retrieval;
- automatic tag, release, package publication, or deployment.

### Future scope requiring a dedicated contract

- MCP facade and Secure MCP Tunnel;
- browser workers;
- Docker workers;
- Unity workers;
- restricted desktop or RPA workers;
- paid-provider handoff;
- webhook ingestion;
- GitHub Checks publication;
- write-capable workers;
- automatic approval for selected repository/manifest pairs;
- remote artifact retrieval;
- production or untrusted multi-tenant operation.

## 6. Working method

### 6.1 Before implementation

1. Establish the user-visible outcome.
2. Inspect current repository and GitHub state.
3. Identify the exact base branch and full starting SHA.
4. Review accepted architecture, active issue, PR, and living plans.
5. Define in-scope and forbidden work.
6. Define acceptance criteria and exact evidence.
7. Determine connector-supported work.
8. Hand only the remaining local work to Codex.

For a material slice, maintain:

- one authoritative issue;
- one canonical branch;
- one draft PR;
- one living ExecPlan under `.agent/execplans/`.

### 6.2 Connector-first workflow

Use the connector to:

- inspect repository metadata and files;
- inspect branches, issues, PRs, reviews, and comments;
- create and update issues, branches, PRs, and text files;
- inspect patches and hosted Actions;
- coordinate labels, reviewers, comments, and review threads;
- merge only after explicit owner authorization.

Use local tools for:

- local checkout verification;
- unpushed state;
- dependency installation;
- implementation;
- formatting, linting, typing, tests, builds, scans, and runtime behavior;
- generated files;
- browser, desktop, Docker, Unity, and platform-specific validation;
- local worktree and branch cleanup.

After local work is pushed, return to the connector for remote verification, patch review, hosted-CI inspection, review cleanup, and owner-decision support.

### 6.3 Codex handoffs

A handoff must specify:

- repository and known local path;
- issue, PR, and branch;
- exact expected local and remote starting SHAs;
- clean-state or preserved-dirty requirements;
- exact in-scope and forbidden work;
- authoritative files and acceptance contract;
- required validation;
- commit and push expectations;
- merge prohibition;
- required final report.

A handoff must direct Codex to stop rather than improvise when:

- repository identity, branch, or SHA differs;
- local state conflicts with the expected continuation;
- unknown dirty files exist;
- a required object is missing;
- destructive recovery would be necessary;
- authorization is insufficient.

### 6.4 Interrupted work

- Verify remote state first.
- Preserve the existing worktree.
- Record local and remote SHAs.
- Inventory staged, unstaged, untracked, and unpublished work.
- Do not reset, clean, stash, rebase, reclone, or start a parallel implementation.
- Resume from the existing continuation state.

### 6.5 Review corrections

1. Record the exact finding.
2. Preserve accepted product behavior.
3. Change only what resolves the blocker.
4. Add a regression.
5. Run affected focused tests.
6. Run the complete required matrix.
7. Update the ExecPlan and PR evidence.
8. Return for connector re-review.

## 7. Technical standards

### 7.1 Architecture

- Keep task coordination and deterministic execution as separate domains.
- Keep `Task`, `WorkOrder`, `ExecutionRun`, and execution leases conceptually and persistently distinct.
- Preserve the control-server plus outbound-worker model.
- Use transactional or database-enforced concurrency for authoritative ownership and reservation.
- Use exact-SHA source identity and immutable manifest identity.
- Preserve read-only target behavior for deterministic workers.
- Prefer additive compatibility-preserving changes.
- Do not use process-local ordering or random choice as the authoritative scheduler.

### 7.2 Repository structure

Use the established structure:

```text
server/                    FastAPI backend
client/python/             Python client and worker
web/                       Operator dashboard and browser tests
scripts/                   Development and operational helpers
docs/                      Architecture, API, guides, reports, operations
.agent/execplans/          Living implementation plans
.github/                   Workflows and repository templates
```

Avoid broad reorganizations during feature work unless the accepted issue requires them.

### 7.3 Command execution

- Use direct fixed argv and `shell=False` or platform-equivalent direct process APIs.
- Enforce explicit environment allowlists.
- Enforce step and overall deadlines.
- Enforce output, storage, artifact-count, artifact-size, and retention limits.
- Terminate the process tree on timeout, cancellation, shutdown, ownership loss, or unproven quiescence.
- Never continue after authoritative ownership is lost.
- Never accept caller-selected executable, argv, path, environment value, parser, or cleanup target.

### 7.4 Filesystem and worktrees

- Use worker-owned disposable exact-SHA worktrees.
- Verify containment after path resolution.
- Reject traversal, rooted paths, symlinks, junctions, reparse points, special files, and unsafe links.
- Protect canonical repository integrity before and after execution.
- Separate canonical source, transient worktree, and evidence roots.
- Verify ownership markers before cleanup or retention pruning.
- Never delete paths not proven worker-owned.

### 7.5 Persistence and migrations

- Persistence changes require compatibility with the prior supported schema.
- Additive startup compatibility must be idempotent.
- Existing databases must start successfully after upgrade.
- Repeated startup must succeed.
- Non-null changes require a migration or safe redesign.
- Add prior-schema and repeated-startup regressions.
- Do not assume ORM table creation alters existing tables.

### 7.6 APIs and schemas

- Use typed bounded request and response contracts.
- Reject unknown fields when strict parsing is part of the trust boundary.
- Exclude executable definitions, secrets, and local paths from normal APIs.
- Use bounded reason codes rather than raw exception text.
- Preserve exact identity and idempotency semantics.
- Prefer additive omitted-field-compatible changes.

### 7.7 Evidence

- Bind compact evidence to repository, exact SHA, manifest identity and digest, environment, dependency inputs, result contract, and artifact hashes where applicable.
- Retain full logs locally.
- Hash retained artifacts with SHA-256.
- Validate regular-file status, containment, byte/count limits, and stability.
- Redact secrets and absolute paths before evidence leaves the worker.
- Reused evidence creates a distinct auditable run linked to immutable source evidence.
- Database metadata alone is not proof that local evidence still exists.

### 7.8 Exact evidence reuse

- `never` remains the default and executes fresh.
- `allow_exact` reuses only after exact identity match and same-worker local proof.
- Failed `allow_exact` proof may fall back to fresh at most once under the same valid lease.
- `require_exact` must not execute validation when proof is unavailable.
- Reuse must not extend or copy source evidence merely because it was used.

### 7.9 Routing and quotas

- `first_available` remains the compatibility default.
- `cheapest_capable` considers only fully eligible actively polling workers.
- Cost, quota, priority, and enabled state are server-owned.
- Use bounded non-negative integers for authoritative decisions.
- Preserve the accepted deterministic tie-break order.
- Reserve quota atomically with capacity, claim, run, and lease creation.
- Prevent overdraw, double consumption, double release, and leaked reservations.
- Hard pins bypass no trust or eligibility check.
- Workers do not self-report cost, quota, or priority.

### 7.10 Tests and validation

- Add focused regressions for material behavior changes and defects.
- Run focused tests before the full suite.
- Run the complete required suite before a material PR is ready.
- Enforce aggregate and configured module coverage thresholds.
- Use file-backed databases and independent sessions for authoritative concurrency tests.
- Keep automated GitHub integration tests offline and credential-free through mocked transports.
- Do not weaken assertions, skip policies, or thresholds merely to pass.

### 7.11 Browser and accessibility

- Run strict browser tests for UI-sensitive or release-sensitive work.
- Set `SWITCHBOARD_STRICT_PLAYWRIGHT=1` so skips fail the strict gate.
- Require zero skips in the strict invocation.
- Validate keyboard behavior, focus, live feedback, responsive containment, and operator-visible errors when relevant.

### 7.12 Security validation

Use repository-current equivalents of:

```text
Bandit
pip-audit
Gitleaks full-history scan
Lychee or the configured link checker
workflow/YAML validation
full-SHA action-pin validation
secret scanning
public-path and credential hygiene
```

Do not regenerate a secret baseline merely to hide a finding. Document every scanner limitation truthfully.

### 7.13 GitHub Actions

- Pin every action to a full 40-character commit SHA.
- Use minimum permissions, normally `contents: read`.
- Set `persist-credentials: false` unless specifically required.
- Use bounded job timeouts.
- Preserve protected lint, typecheck, test, security, secrets, link, coverage, browser, and accepted workload gates.
- Do not weaken workflow policy to avoid startup or validation failures.

### 7.14 Dependencies

- Review major upgrades separately.
- Document dependency additions, removals, and upgrades.
- Verify applicable license compatibility.
- Run dependency integrity and vulnerability checks.
- Do not merge automated dependency PRs solely to clear a queue.

### 7.15 Commit messages

Use Conventional Commits:

```text
type(scope?): description
```

Established types include:

```text
feat fix docs refactor test build ci chore
```

### 7.16 TODO policy

Use the repository’s accepted form:

```text
TODO(Px, <effort>)
FIXME(Px, <effort>)
```

Run the repository TODO validator.

## 8. Data, privacy, and security

### Secrets

- Secrets come from environment-specific storage or ignored local sources.
- Never commit real tokens.
- Do not place secrets in commands, logs, evidence, comments, screenshots, examples, or fixtures.
- Example values must be unmistakably fake.
- Credentials remain only on components that require them.
- Workers receive only the scoped credential allowed by the accepted architecture.

### Personal and machine information

Normal or public evidence must not include:

- personal data unrelated to repository attribution;
- workstation or user names;
- local absolute paths;
- environment dumps;
- private network details;
- private repositories;
- unrelated process lists;
- machine identifiers;
- unrestricted capability inventories.

### Logs and evidence

Full local evidence must:

- remain under worker-owned roots;
- have bounded retention;
- use ownership markers;
- be excluded from Git;
- be deleted only through marker-verified contained cleanup.

Compact evidence should contain only identity, normalized step results, bounded failure summaries, safe artifact references/hashes, route provenance, cleanup state, and working-tree integrity.

### Network

- Worker communication remains outbound.
- Network policy is operator-controlled.
- Dependency access should be limited to required registries where practical.
- Automated tests remain offline unless a specific integration is authorized.
- A secure tunnel must be typed and allowlisted, not a general proxy.

### Destructive operations

Deleting or modifying user-owned data requires explicit owner authorization.

Automatic cleanup is limited to expired, runner-owned, marker-verified resources. Never use broad deletion commands against a repository or parent working directory.

### Vulnerabilities

Do not file suspected vulnerabilities as public issues. Use private GitHub Security Advisory reporting when available, and avoid publishing exploit details.

## 9. Communication standards

### Normalized statuses

| Status | Meaning |
|---|---|
| `pass` | The required check executed and passed. |
| `fail` | The check executed and found a repository or product failure. |
| `environment-blocked` | The check could not execute because of environment, permission, tool, or infrastructure. |
| `needs-review` | Execution completed but semantic or owner review remains. |
| `draft` | Work remains under implementation or review and must not merge. |
| `ready for owner decision` | Implementation and evidence are complete; owner action remains. |
| `unverified` | Adequate execution evidence does not exist. |
| `stale` | Evidence applies to an older SHA or state. |
| `partial` | Some work completed but the accepted contract is not satisfied. |

### Completion reporting

Distinguish:

- implementation complete;
- local validation complete;
- hosted validation complete;
- connector review complete;
- owner merge or release decision complete.

A final report normally includes repository, issue, PR, branch, starting SHA, final SHA, commits, file scope, local evidence, hosted evidence, connector review, blockers, exact next action, and merge authorization state.

### Public wording

Public material omits local paths, private operational detail, environment dumps, raw logs, unsupported counts, actual-looking tokens, private vulnerabilities, and production claims.

Transient counts, percentages, workflow IDs, and SHAs belong in active PRs, ExecPlans, dated status reports, and release audits—not permanent README or ruleset claims.

## 10. Definition of done

Work is complete only when:

1. Accepted behavior is implemented within scope.
2. Material regressions are covered.
3. Relevant documentation is updated.
4. Migration and rollback behavior are documented where applicable.
5. Focused local tests pass.
6. The complete required local matrix passes or exact blockers are recorded.
7. The working tree is clean.
8. Changes are committed and pushed normally.
9. The remote branch matches the reported SHA.
10. Hosted Commitlint and the complete required CI matrix pass.
11. Connector review finds no unresolved blocker.
12. Review threads are resolved or explicitly dispositioned.
13. The living ExecPlan is current.
14. PR readiness is truthful.
15. No merge, release, deployment, or production claim occurs without owner authorization.

## 11. Git and repository rules

### Branches

- Start from current reviewed `main`.
- Use one canonical branch per accepted work slice.
- Use descriptive names such as `feat/`, `fix/`, `test/`, `docs/`, `release/`, or `chore/`.
- Do not create replacement branches merely because work is difficult.
- Preserve active and recovery branches until their authority is resolved.
- Do not rebase a shared branch without explicit authorization.

### Pull requests

- Open material implementation PRs as draft.
- Keep them draft during implementation and validation.
- Maintain exact base, head, scope, evidence, blockers, exclusions, and merge boundary in the PR body.
- Prefer one consolidated evidence comment over repeated noisy comments.
- Do not mark ready while a known blocker remains.
- Ready does not mean authorized to merge.

### Merge

- Explicit owner authorization is mandatory.
- Use squash merge.
- Supply the expected full head SHA.
- Abort on head movement or changed state.
- Do not enable auto-merge.
- Report the resulting main SHA.
- Close the issue only when its contract says merge completes it.

### Local cleanup

A local branch or worktree may be removed only when:

- its work is merged or explicitly superseded;
- no uncommitted or unpublished work remains;
- no unique evidence or recovery purpose remains;
- ownership and containment are clear.

A remote branch showing `gone` is not sufficient evidence by itself.

## 12. Deliverable standards

### Living ExecPlans

Material work maintains a self-contained ExecPlan under `.agent/execplans/` with current:

- `Purpose / Big Picture`;
- `Progress`;
- `Surprises & Discoveries`;
- `Decision Log`;
- `Outcomes & Retrospective`;
- `Context and Orientation`;
- `Plan of Work`;
- `Concrete Steps`;
- `Validation and Acceptance`;
- `Idempotence and Recovery`;
- `Artifacts and Notes`;
- `Interfaces and Dependencies`.

### Issues

Issue bodies include parent, purpose, exact base when known, accepted behavior, security and compatibility boundaries, tests, documentation, exclusions, and definition of done.

### PRs

PR bodies include repository, base and base SHA, branch, exact head, state, scope, delivered behavior, exclusions, local evidence, hosted evidence, connector review, blockers, and merge boundary.

### Evidence records

Structured evidence should contain equivalent fields for job/run ID, status, repository, requested and executed SHA, trusted profile, normalized steps, bounded failure, artifact hashes, route/reuse provenance, cleanup, and working-tree integrity.

### Documentation

Behavior changes update applicable authoritative files, including README, API, configuration, architecture, operations, status, dependencies, historical audits, and the living ExecPlan.

Historical evidence documents must be clearly labeled as historical and must not be silently rewritten into current-state documents.

## 13. Approval and escalation

### May proceed within an accepted issue

- repository inspection;
- architecture analysis;
- plans and acceptance criteria;
- approved branch documentation;
- factual issue/PR coordination;
- authorized read-only verification;
- implementation and focused tests within scope;
- normal commits and pushes to the approved feature branch when explicitly allowed.

### Requires explicit owner approval

- merging;
- tags, releases, package publication, or deployment;
- visibility changes;
- paid services;
- production or repository secrets;
- expanded network exposure;
- branch protection, rulesets, or security-product changes;
- force-push or history rewriting;
- deletion of active or unmerged work;
- destructive migrations or user-data deletion;
- architecture changes outside the accepted issue;
- write-capable workers;
- automatic approval or merge;
- arbitrary shell or unrestricted file access;
- publication of vulnerability details.

### Stop and escalate

Stop when:

- a secret may be exposed;
- a path escapes its root;
- evidence contains a prohibited local path;
- manifest identity or digest mismatches;
- ownership is lost;
- cleanup ownership is uncertain;
- a migration may corrupt data;
- GitHub actor, repository, PR, comment, or head identity cannot be verified;
- a network or provider action exceeds policy;
- authorization is ambiguous for a consequential action.

## 14. Change log

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-24 | Normalize the Project ruleset into stable repository governance without moving status fields. |
