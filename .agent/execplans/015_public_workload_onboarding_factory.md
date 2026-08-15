# Build a repeatable public workload onboarding factory

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Switchboard can already execute approved fixed manifests against exact source revisions, route work to capable outbound local workers, retain full evidence locally, publish bounded evidence, and reuse exact evidence only after same-worker cryptographic proof. The current external workload catalog is still bespoke: every new repository requires manual catalog, manifest, parser, readiness, test-fixture, UI, and documentation work.

This slice turns that bespoke process into a repeatable source-controlled onboarding factory without turning Switchboard into a remote shell or a runtime profile interpreter. An operator should be able to review a public repository contract, add one reviewed Python profile definition, validate the complete catalog deterministically, see profile readiness in the Validation Broker, run a fresh exact-SHA validation, and reuse the result only when every result-affecting identity still matches.

The slice proves the factory with two additional public repositories:

- `Nobodyworld/dev-logger-zscripts` through `validate-zscripts@1`;
- `Nobodyworld/app-industry-resilience` through `validate-industry-resilience@1`.

`Nobodyworld/app-accounting-modular` remains the existing external reference profile. Existing Switchboard manifests remain unchanged.

Observable completion means:

1. `python scripts/dev.py validate-workload-catalog` validates exactly four public catalog entries without executing target code or opening the network.
2. The Validation Broker shows safe bounded readiness for each default profile.
3. Committed synthetic production-path acceptances prove fresh execution and same-worker exact reuse for both new profiles.
4. The Zscripts live-PR attempt is recorded truthfully as target-state-blocked because planned PR #119 merged.
5. Controlled read-only dogfood runs against the exact current Industry Resilience PR #130 head, or a precise target/environment blocker is recorded.
6. Complete local and hosted validation passes on one final branch head.

The repository remains a **PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY**. This slice does not authorize production deployment, public internet exposure, untrusted multi-tenant use, paid-provider execution, MCP, desktop/RPA expansion, or write-capable workers.

## Progress

- [x] Maintenance convergence merged through PR #144.
- [x] Starting `main` locked to `eef4df6c43807576bf1c067200b44f16d6dd8e31`.
- [x] Canonical branch `feat/public-workload-onboarding-factory` created from the exact starting SHA.
- [x] Governing issue #143 authorized as the active large slice.
- [x] Current Zscripts and Industry Resilience contract sources inspected through GitHub.
- [ ] Establish safe local worktree and isolated environments without disturbing unknown user work.
- [ ] Record baseline tests and exact external target observations.
- [ ] Implement the source-controlled profile factory and deterministic catalog validator.
- [ ] Preserve the three existing manifest digests exactly.
- [ ] Add reviewed `validate-zscripts@1` definition and catalog association.
- [ ] Add reviewed `validate-industry-resilience@1` definition and catalog association.
- [ ] Add truthful pnpm capability discovery and matching.
- [ ] Add bounded read-only catalog readiness projection and API.
- [ ] Extend the Validation Broker readiness UI and bounded history.
- [ ] Add committed synthetic fresh/reuse production-path proofs for both new profiles.
- [ ] Add isolated hosted acceptance jobs with exact result enforcement.
- [ ] Attempt controlled read-only Industry Resilience live dogfood or record a precise blocker.
- [ ] Record the Zscripts merged-target blocker without substituting another PR.
- [ ] Complete adversarial security review.
- [ ] Complete focused and full local validation.
- [ ] Push the final branch and record exact local/remote SHA parity.
- [ ] Complete ultimate-head hosted validation and connector review.

## Surprises & Discoveries

- Observation: `docs/reports/status.md` on the starting baseline still describes `83f84a7...` and draft PR #139 even though current `main` is `eef4df6...` and PR #144 has already merged.
  Evidence: The file at the starting SHA still contains the earlier PR #139 status block. This slice begins by reconciling the durable status document.

- Observation: The originally planned Zscripts live target, PR #119, is closed and merged. Zscripts `main` has since advanced to `c96628e2409dbb4d184030fc29fd431050b3009c`.
  Evidence: GitHub reports PR #119 merged and the protected current Zscripts `main` at `c96628e...`.

- Observation: Zscripts now has a deterministic documentation-link validator and a protected quality helper with fixed named operations. Its current protected environment is Python 3.11, Node 24.12.0, and pnpm 10.18.1.
  Evidence: `scripts/quality_gate.py`, `.github/workflows/ci.yml`, `pyproject.toml`, and `workspace-ui/package.json` at `c96628e...`.

- Observation: Industry Resilience PR #130 remains open, draft, and mergeable at `5e458da35accc9fedd9f29a521de5c27b757a8d0`; its CI Quality Gate and Docker Smoke are green.
  Evidence: GitHub PR metadata and workflow runs `31553906171` and `31553906099`.

- Observation: The current Switchboard worker advertises Python and Node versions but does not independently discover a pnpm version.
  Evidence: `client/python/execution_worker/capabilities.py` at the starting SHA.

## Decision Log

- Decision: Use one canonical branch and one draft PR for the complete slice.
  Rationale: The owner prefers large coherent slices; shared catalog, readiness, worker, UI, tests, CI, and documentation changes must converge on one reviewed head.
  Date/Author: 2026-08-15 / Owner and GitHub coordinator.

- Decision: Create the branch, initial ExecPlan, and draft PR through the GitHub connector before local implementation.
  Rationale: These are supported remote coordination operations and do not require local execution. Codex should be reserved for local implementation, test execution, and live dogfood.
  Date/Author: 2026-08-15 / GitHub coordinator.

- Decision: Preserve the existing digest algorithm and exact digests for `worker-smoke@1`, `validate-switchboard@1`, and `validate-accounting-modular@1`.
  Rationale: Historical work orders, runs, evidence, and reuse fingerprints already bind to those immutable identities. New factory functionality must be additive.
  Date/Author: 2026-08-15 / Issue #143 contract.

- Decision: Keep executable profile definitions in reviewed Python source.
  Rationale: Runtime YAML, JSON, TOML, database rows, API input, and target repository metadata must never become executable merely by passing a schema.
  Date/Author: 2026-08-15 / Issue #143 contract.

- Decision: Treat Zscripts live dogfood as target-state-blocked and do not substitute another pull request.
  Rationale: Exact-PR evidence must remain tied to the accepted target. Running current `main` would not prove the planned live PR path.
  Date/Author: 2026-08-15 / Owner authorization.

- Decision: Translate the Industry Resilience `make quality-gate` contract into fixed direct argv.
  Rationale: The generic worker must not require GNU Make on Windows, and the caller must not choose a command or target.
  Date/Author: 2026-08-15 / Issue #143 contract.

- Decision: Keep deterministic target validation separate from attended/manual gates.
  Rationale: The Industry profile must not claim Docker, Edge, Playwright, screen-reader, release, or publication acceptance; the Zscripts profile must not claim semantic correctness of performance conclusions.
  Date/Author: 2026-08-15 / Issue #143 contract.

## Outcomes & Retrospective

No implementation outcome is claimed yet. This section must be replaced with exact final behavior, test counts, coverage, external target evidence, limitations, and lessons before the branch is declared ready for connector review.

## Context and Orientation

The main implementation surfaces are:

- `server/execution/catalog.py`: strict public repository-to-manifest associations and safe display metadata.
- `server/execution/registry.py`: immutable trusted manifests, fixed steps, environment policy, artifacts, required capabilities, dependency identity paths, and manifest digests.
- `server/execution/capabilities.py`: authoritative capability matching used by routing and readiness.
- `server/execution/routing.py`: deterministic route eligibility and selection.
- `server/execution/service.py`: work-order lifecycle, assessment, checkout, leases, quota, capacity, and execution ownership.
- `server/execution/operator_projection.py`: bounded operator history and overview projections.
- `server/execution/schemas.py`: strict request and response contracts.
- `server/api/routers/execution.py`: catalog, readiness, operator, and work-order API routes.
- `client/python/execution_worker/capabilities.py`: bounded host capability discovery.
- `client/python/execution_worker/config.py`: operator-owned repository mappings and worker configuration.
- `client/python/execution_worker/worker.py`: outbound worker loop and exact-SHA execution lifecycle.
- `client/python/execution_worker/runner.py`: fixed-argv subprocess execution, cancellation, process-tree termination, output bounds, and cleanup.
- `client/python/execution_worker/evidence.py`: local evidence retention and exact reuse proof.
- `web/static/validation_broker.js`: Validation Broker operator workflow.
- `web/tests/test_ui.py`: strict browser acceptance.
- `scripts/dev.py`: developer validation commands.
- `.github/workflows/ci.yml`: protected hosted validation matrix.
- `server/tests/test_execution_catalog.py`: canonical manifest/catalog digest and pairing regressions.
- `server/tests/test_execution_routing.py`: route and readiness behavior.
- `client/python/tests/test_execution_worker_server_smoke.py`: real server/client/local-worker production-path acceptance.
- `docs/operations/trusted-workload-onboarding.md`: workload review and onboarding guidance.
- `docs/operations/validation-command-center.md`: operator workflow.
- `docs/architecture/local-execution-broker.md`: trust and data-flow architecture.

The starting catalog contains:

- `Nobodyworld/dev-agent-switchboard`;
- `Nobodyworld/app-accounting-modular`.

The final public catalog must contain exactly:

- `Nobodyworld/dev-agent-switchboard`;
- `Nobodyworld/app-accounting-modular`;
- `Nobodyworld/dev-logger-zscripts`;
- `Nobodyworld/app-industry-resilience`.

The exact legacy manifest digests that must not move are:

- `worker-smoke@1`: `63e645f19d8c60ae442e1800aaecc1a18a719d53f22ba8e85ec62bf745ed55d1`;
- `validate-switchboard@1`: `10e99418e4e6f0e9f4a6e95fb5b9a267dab4eeac4671cf58533c8b9afe1fed98`;
- `validate-accounting-modular@1`: `892f1269cdf2a6f4e0df4d86879e5dae980374d598faeadee77c2c32f33aa612`.

The pre-slice catalog digest is `3e8fe68e917d1afa5615e158f3ef69ac78193f356502c8e6fb071799edad5436`. The final catalog digest is expected to change because two reviewed repositories are added.

## Plan of Work

### 1. Establish a safe implementation environment

Inspect the protected primary checkout, remotes, worktrees, branches, and stashes. Preserve unknown user work and the known `security-deferral-wip` stash. Fetch and prune normally. If the primary checkout can be fast-forwarded safely, update it with `--ff-only`; otherwise leave it untouched and create a dedicated worktree from the connector-created remote feature branch.

Use isolated environments and a campaign-owned temporary root on a filesystem with adequate free space. Do not use broad cleanup commands or delete unknown paths.

### 2. Reconcile durable status and baseline evidence

Update `docs/reports/status.md` to the exact starting baseline and active issue/branch/PR. Record baseline focused tests before changing execution architecture. Keep public-preview wording accurate.

### 3. Build the source-controlled profile factory

Introduce a typed, additive factory that compiles reviewed Python definitions into the existing trusted manifest and catalog surfaces. Separate display-only metadata from execution identity. Define strict result contracts and bounded profile-level limits. Preserve legacy manifest construction and digests.

Fail closed on unknown fields, duplicate identities or steps, unsafe paths, unsupported parsers, caller-controllable execution values, invalid environment keys/values, missing result-affecting inputs, repository/profile mismatch, private repositories, and unbounded limits.

Add `python scripts/dev.py validate-workload-catalog`. It must perform no target execution, network operation, database mutation, capacity/quota reservation, or source fetch.

### 4. Add truthful package-manager capability matching

Discover pnpm only through fixed bounded `pnpm --version` execution with `shell=False`. Report a safe bounded version capability. Enforce the exact Zscripts package-manager contract. Preserve compatibility for old workers and existing profiles.

### 5. Onboard Zscripts

Review current Zscripts `main` before finalizing the profile. Bind the reviewed fixed helper and operation inventory, Python/Node/pnpm requirements, network/write policy, result-affecting inputs, result contract, artifact declarations, and semantic exclusions into immutable source-controlled identity.

Retain bounded summaries and hashes only. Keep full logs and generated package/build bytes local. Do not include optional ML/Torch/GPU work.

### 6. Onboard Industry Resilience

Re-resolve PR #130 before implementation. Translate its protected Makefile gate into fixed direct argv under Python 3.13. Bind requirements, workflow, benchmark script, secret baseline, coverage paths and threshold, audit policy, result contract, artifacts, and exclusions into identity.

Do not invoke GNU Make, provider refreshes, Docker, target Playwright, Edge, screen readers, release, or publication through the generic profile.

### 7. Add bounded catalog readiness and history

Implement a batch catalog readiness projection that evaluates each default profile through the existing authoritative eligibility evaluator using one bounded worker snapshot. It must be read-only and must not refresh liveness, reserve quota/capacity, create work orders/runs, fetch source, or resolve arbitrary URLs.

Expose only safe repository/profile identity, digest prefix, normalized runtime requirements, ready count, bounded blocker, recent fresh/reused summary, source-availability caveat, and manual/semantic exclusions. Reuse existing persisted data whenever possible rather than adding duplicative schema.

### 8. Extend the Validation Broker

Render exactly four public catalog entries. Show truthful readiness and mismatch reasons, latest result, fresh/reused state, and scope exclusions without exposing commands, argv, environment values, local paths, tokens, credentials, private repositories, or arbitrary capability documents.

Preserve keyboard flow, visible focus, live feedback, existing request/approval/route/quota/publication/history behavior, desktop containment, and 390-pixel containment.

### 9. Prove both profiles synthetically through the production path

Create committed minimal synthetic repositories and exact selectors for Zscripts and Industry Resilience. Use the real FastAPI server, `ExecutionClient`, `LocalWorker`, evidence store, exact-SHA worktrees, fixed steps, explicit approval, fresh execution, retained local evidence, and same-worker exact reuse.

Prove mismatch refusal before mutation, exact expected step inventory, bounded result parsing, artifact hashes, canonical source integrity, zero repeated steps on reuse, invalidation on every result-affecting change, route/source provenance, avoided-work counts, and complete cleanup.

Synthetic evidence must always be labeled synthetic and must not be represented as execution of either real external repository.

### 10. Add isolated hosted acceptance jobs

Preserve current Python 3.11 protected jobs and the Python 3.12 Accounting workload acceptance. Add:

- `Zscripts workload acceptance` under Python 3.11, Node 24.12.0, and pnpm 10.18.1;
- `Industry Resilience workload acceptance` under Python 3.13.

Use full 40-character action pins, minimal permissions, disabled persisted credentials, bounded timeouts, exact selectors, exact JUnit test-count enforcement, zero skips, and no external repository checkout or sensitive artifacts.

### 11. Attempt controlled Industry Resilience live dogfood

Immediately before execution, re-resolve PR #130. Use an existing operator-approved canonical checkout, isolated exact-SHA worktree, compatible Python 3.13 environment, real outbound worker, real GitHub adapter, explicit fresh approval, and a distinct explicit `allow_exact` reuse request.

Do not modify or publish to the target. Verify canonical source integrity, zero repeated validation steps on reuse, route/reuse provenance, worker shutdown, and cleanup. If any prerequisite is unavailable, record the exact blocker without substituting another target or fabricating success.

### 12. Complete adversarial review, full validation, documentation, and cleanup

Review the complete diff for command injection, runtime-authored execution, unsafe paths/artifacts/environments, private/local/credential disclosure, readiness mutation, reuse identity gaps, external writes, synthetic/live ambiguity, manual-gate overclaiming, process leaks, and weakened CI.

Run the full local matrix, strict browser tests with zero skips, process termination stress on Windows and Linux/WSL where available, all coverage thresholds, security/dependency/secret/link scans, workflow validation, and public hygiene.

Update this plan and all affected public documentation. Push normally. Keep the PR draft and unmerged for hosted validation and connector review.

## Concrete Steps

The implementation agent must resolve exact current commands from the branch and target repositories rather than treating this section as a substitute for source inspection.

1. Verify `origin/main` remains `eef4df6c43807576bf1c067200b44f16d6dd8e31` and the remote feature branch contains only connector-created planning commits.
2. Create a dedicated worktree for `feat/public-workload-onboarding-factory` without modifying unknown primary-checkout state.
3. Create fresh Python 3.11 and 3.12 environments; add Python 3.13 and Node/pnpm environments as required by the new acceptances.
4. Run focused baseline catalog, routing, worker/evidence/reuse, accounting acceptance, and strict UI availability tests.
5. Implement and test the profile factory and catalog validator.
6. Implement and test pnpm discovery and capability matching.
7. Implement and test both profile definitions.
8. Implement and test catalog readiness projection, API, and history.
9. Implement and test Validation Broker UI behavior.
10. Implement and test both synthetic production-path acceptances.
11. Implement and validate hosted workflow jobs.
12. Re-resolve and attempt Industry Resilience dogfood or record the exact blocker.
13. Run adversarial review and correct material findings.
14. Run the complete local matrix.
15. Update this plan, status documentation, operator documentation, and PR evidence.
16. Commit logical Conventional Commit units and push normally.

Expected developer checks include the repository-current equivalents of:

    python scripts/dev.py validate-workload-catalog
    pre-commit run --all-files --show-diff-on-failure
    python scripts/dev.py check-todos --root .
    python -m ruff check .
    python -m ruff format --check .
    python -m black --check .
    python -m mypy --config-file mypy.ini server client scripts
    python -m pytest
    SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py --junitxml=reports/pytest-ui.xml -rA
    python -m bandit -q -r server -x server/tests
    python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
    gitleaks detect --verbose
    git diff --check

Use the exact current coverage command and enforce all existing module thresholds. Add explicit meaningful coverage enforcement for new security-critical profile-validation and catalog-readiness modules.

## Validation and Acceptance

The slice is acceptable only when all of the following are true on one exact final branch head:

- The catalog contains exactly four approved public repositories.
- The three legacy manifest digests are unchanged.
- The new Zscripts and Industry manifest definitions serialize and digest deterministically.
- Display-only metadata cannot silently affect execution identity, while every execution/result/reuse-relevant field does.
- `validate-workload-catalog` is deterministic, bounded, offline, non-mutating, and rejects all unsafe definitions.
- Worker capability discovery reports pnpm truthfully and safely.
- Readiness, route assessment, and checkout agree for both new profiles.
- Batch readiness performs no persistence mutation or source/network operation.
- The Validation Broker renders safe accurate rows and mismatch states with accessible responsive behavior.
- Both synthetic profile acceptances prove fresh execution and exact reuse through real production components.
- Reuse invalidates on commit, manifest, runtime, result contract, artifact, environment, network/write policy, and result-affecting input changes.
- Zscripts live dogfood is recorded as target-state-blocked with no substitute PR.
- Industry Resilience live dogfood succeeds against an exact current open head or has a precise truthful blocker.
- No external repository or PR is modified.
- Full pytest passes with only explicitly expected platform/runtime skips.
- Strict Playwright executes with zero skips.
- Existing and new coverage thresholds pass.
- Formatting, lint, typing, TODO, security, dependency, secret, link, workflow, diff, and public-hygiene gates pass.
- Windows and Linux/WSL process cancellation and cleanup remain green where the environments are available.
- The worktree is clean, the branch is pushed normally, and local/remote SHAs match.
- The PR remains draft and unmerged until final connector review and separate expected-head owner authorization.

## Idempotence and Recovery

- All profile definitions are source-controlled and deterministic; repeated catalog validation must produce the same result.
- Schema/startup changes, if any, must be additive and safe across repeated startup and prior supported databases.
- Synthetic acceptance fixtures must create and clean only marker-owned temporary resources.
- External dogfood must use disposable exact-SHA worktrees and leave canonical repositories unchanged.
- If the local primary checkout is dirty, leave it untouched and use an isolated worktree.
- Never reset, clean, stash, or overwrite unknown user work.
- Preserve `security-deferral-wip` and all unrelated branches/worktrees/stashes.
- If `origin/main`, the feature branch, Zscripts contract, or Industry PR head moves unexpectedly, stop or record the exact observation before proceeding; do not substitute SHAs silently.
- If a process, worktree, evidence path, or cleanup target cannot be proven campaign-owned and contained, retain it and report it.
- If complete validation cannot run, record the exact environment or target blocker. Do not weaken or skip the gate.

## Artifacts and Notes

Retain one compact sanitized local evidence directory outside the repository. It should contain environment and exact-ref inventory, commands and exit codes, focused/full test summaries, JUnit summaries, coverage results, profile/catalog digests, synthetic acceptance summaries, process-stress summary, scanner summaries, external target-state evidence, dogfood result or blocker, and cleanup inventory.

Do not commit or remotely publish local absolute paths, credentials, environment dumps, full logs, node modules, virtual environments, external source copies, screenshots containing private data, wheel/zipapp bytes, or unbounded generated reports.

The initial branch and this plan were created through the GitHub connector because those operations do not require local execution. Local implementation, dependency installation, runtime testing, browser testing, process stress, and external dogfood remain the local-agent boundary.

## Interfaces and Dependencies

The final implementation must expose or preserve stable typed interfaces equivalent to:

- a source-controlled `TrustedWorkloadProfile` or similarly named immutable definition type;
- a compiler/validator that produces existing `TrustedManifest` and `TrustedRepository` surfaces without changing legacy identities;
- a source-controlled result-contract type using a fixed supported parser vocabulary;
- deterministic profile and catalog digest functions;
- `python scripts/dev.py validate-workload-catalog`;
- bounded pnpm capability discovery and matching;
- a bounded read-only catalog readiness response model and endpoint;
- safe Validation Broker catalog readiness rendering;
- exact synthetic acceptance selectors for Zscripts and Industry Resilience;
- isolated hosted jobs with exact result enforcement.

The design must continue to use fixed argument vectors, direct process APIs, explicit environment allowlists, read-only target repositories, exact source SHAs, outbound workers, bounded/redacted remote evidence, worker-local full logs, explicit approval, deterministic routing, atomic ownership, and same-worker exact evidence proof.
