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
- [x] Establish safe local worktree and isolated environments without disturbing unknown user work.
- [x] Record baseline tests and initial exact external target observations.
- [x] Implement the source-controlled profile factory and deterministic catalog validator.
- [x] Preserve the three existing manifest digests exactly.
- [x] Add reviewed `validate-zscripts@1` definition and catalog association.
- [x] Add reviewed `validate-industry-resilience@1` definition and catalog association.
- [x] Add truthful pnpm capability discovery and matching.
- [x] Add bounded read-only catalog readiness projection and API.
- [x] Extend the Validation Broker readiness UI and bounded history.
- [x] Add committed synthetic fresh/reuse production-path proofs for both new profiles.
- [x] Add isolated hosted acceptance jobs with exact result enforcement.
- [x] Record the precise Industry Resilience live-dogfood blocker; do not execute it on this worker.
- [x] Record the Zscripts merged-target blocker without substituting another PR.
- [x] Complete adversarial security review and apply the bounded in-slice remediations.
- [x] Complete every locally available final validation gate and record exact blockers: `pip-audit` stalled without a response, Docker is unavailable, `git fsck --full` cannot read the shared object store inside the sandbox, and the hostile-public-target isolation boundary remains unsatisfied.
- [ ] Push the final branch normally and record exact local/remote SHA parity; publication is limited to source review on the existing draft PR and does not claim live-public-workload readiness.
- [ ] Complete ultimate-head hosted validation and connector review.

## Surprises & Discoveries

- Observation: `docs/reports/status.md` on the starting baseline still describes `83f84a7...` and draft PR #139 even though current `main` is `eef4df6...` and PR #144 has already merged.
  Evidence: The file at the starting SHA still contains the earlier PR #139 status block. This slice begins by reconciling the durable status document.

- Observation: A read-only GitHub re-resolution at `2026-08-21T22:10:14Z` found the originally planned Zscripts live target, PR #119, closed and merged at head `5fbb3a219d04ea3631042ef3a98272e1b5fca579`; protected Zscripts `main` remains `c96628e2409dbb4d184030fc29fd431050b3009c`.
  Evidence: GitHub branch and PR metadata report PR #119 merged at `2026-08-12T05:50:35Z` and protected current Zscripts `main` at `c96628e...`.

- Observation: Zscripts now has a deterministic documentation-link validator and a protected quality helper with fixed named operations. Its current protected environment is Python 3.11, Node 24.12.0, and pnpm 10.18.1.
  Evidence: `scripts/quality_gate.py`, `.github/workflows/ci.yml`, `pyproject.toml`, and `workspace-ui/package.json` at `c96628e...`.

- Observation: A read-only GitHub re-resolution at `2026-08-22T00:56:48Z` found Industry Resilience PR #130 still open, draft, cleanly mergeable, and unmerged at `e3fea89db624414fe3cad7980768f0265cf9570a`; exact-head CI and Docker Smoke remain green.
  Evidence: GitHub PR metadata, CI run `32536731040`, and Docker Smoke run `32536731320`. The current head is three commits beyond the 2026-08-21 checkpoint `01c4ebf52fcae3cce8771371228723db772d1459` and six commits beyond historical head `5e458da35accc9fedd9f29a521de5c27b757a8d0`. The latest delta changes only Streamlit configuration/UI, public API/pipeline behavior, tests, and documentation. GitHub content metadata shows that all six reviewed profile-contract files retain identical blob IDs across both target movements.

- Observation: The current Switchboard worker advertises Python and Node versions but does not independently discover a pnpm version.
  Evidence: `client/python/execution_worker/capabilities.py` at the starting SHA.

- Observation: The protected primary checkout was clean on `main`, three commits behind the accepted base, and had no local-only commits. It was safely fast-forwarded; the feature work continues in one clean isolated worktree at the connector-prepared head.
  Evidence: Exact `origin/main`, feature head, merge base, and `0 behind / 6 ahead` checks matched the accepted values; `git fsck --full --no-dangling` passed.

- Observation: The machine-wide Python installation had unrelated dependency conflicts, so it is not valid validation evidence for this slice.
  Evidence: Global `python -m pip check` reported unrelated `opencv-python`/NumPy and Streamlit/Pillow conflicts. Fresh campaign-scoped Python 3.11, 3.12, and 3.13 runtimes and isolated virtual environments were provisioned instead.

- Observation: The connector's reuse clock fixture is tightly scoped to `test_execution_reuse` and injects the fixed July 30 synthetic instant into test-only service/module clocks.
  Evidence: The exact selector passed once and the complete `server/tests/test_execution_reuse.py` module passed 15 tests on the connector-prepared head. Production retention code was not changed.

- Observation: The literal Industry Resilience secret-baseline hook validates its baseline without scanning source paths when invoked with no positional filenames.
  Evidence: The reviewed Make target and `detect-secrets` pre-commit entry point take no source-file arguments. This profile must record that bounded semantic exclusion rather than claim a full source secret audit.

- Observation: Persisted JSON turns tuple-shaped source values into lists on a repeated application lifespan.
  Evidence: The first factory compiler revision produced `trusted_manifest_digest_conflict` on a second startup; normalizing the compiled source mappings to JSON-shaped lists restored repeat-startup integrity without changing any legacy manifest.

- Observation: The reviewed Zscripts helper's summary intentionally does not provide an authoritative test-count/skips field.
  Evidence: The helper's `quality-summary.json` reports its fixed ordered operation inventory, status, coverage threshold, and duration. The closed parser validates those reports and does not infer a test count from helper details.

- Observation: Strict host containment is not a sufficient public-target isolation boundary on a same-account worker.
  Evidence: Native Windows Job Object and WSL/Linux subreaper regressions prove bounded ordinary-process cleanup, but an independently adversarial review found same-identity credential/Git-state exposure and a Linux `CLONE_PARENT` plus `setsid()` escape outside the host descendant tree. The current machine has no operator-provided separate identity/container/ACL boundary. Live public-target dogfood is therefore blocked rather than treated as safe evidence.

- Observation: The first final full-suite run found a terminal-reason compatibility regression introduced by the conservative runner-exception quarantine path.
  Evidence: `test_runner_exception_without_cancellation_remains_failed` expected the long-standing bounded `worker_error:RuntimeError` reason and received `worker_execution_error:RuntimeError`. Restoring the legacy reason retained quarantine while the final serial run passed `682` tests with `16` documented platform/fixture skips and no failures or errors.

- Observation: The final publication `pip-audit` query did not produce an advisory response during its bounded 60-second attempt.
  Evidence: The task-owned process was interrupted and confirmed absent afterward. This is an environment-limited scanner result, not a passing audit or a product assertion failure. It agrees with the earlier campaign attempt that remained live without an active socket until safely terminated.

- Observation: `git fsck --full` cannot inspect the shared object store from this sandbox.
  Evidence: The single required attempt failed with `Permission denied` while mmap-opening loose objects under the shared `.git/objects` directory. No permission, object-store, or repository repair was attempted; exact ref/diff/commit operations succeed when narrowly approved outside the sandbox.

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

- Decision: Retain the reviewed `validate-industry-resilience@1` source definition after re-resolving PR #130 at `e3fea89db624414fe3cad7980768f0265cf9570a`.
  Rationale: The six commits since `5e458da...`, including the latest three since `01c4ebf...`, do not change `Makefile`, `.github/workflows/ci.yml`, `requirements.txt`, `requirements-dev.txt`, `config/.secrets.baseline`, or `src/scripts/benchmark_metrics.py`; GitHub reports identical blob IDs for every reviewed profile-contract file. The deterministic profile contract has therefore not moved. This does not authorize live execution; the target must be resolved again immediately before any later attempt.
  Date/Author: 2026-08-21 / Owner contract and local implementation coordinator.

- Decision: Treat PR #145's current body and issue #143's latest coordination comment as authoritative for external target disposition.
  Rationale: Both current GitHub coordination surfaces supersede older target observations in this living plan. Their Zscripts `TARGET-STATE-BLOCKED` and Industry `ENVIRONMENT-BLOCKED` boundaries match the independent read-only GitHub re-resolution recorded above.
  Date/Author: 2026-08-21 / Owner contract and local implementation coordinator.

- Decision: Keep deterministic target validation separate from attended/manual gates.
  Rationale: The Industry profile must not claim Docker, Edge, Playwright, screen-reader, release, or publication acceptance; the Zscripts profile must not claim semantic correctness of performance conclusions.
  Date/Author: 2026-08-15 / Issue #143 contract.

- Decision: Use campaign-scoped managed Python runtimes and browser assets for validation.
  Rationale: It provides the requested Python 3.11/3.12/3.13 evidence without modifying the system toolchain or relying on unrelated global packages.
  Date/Author: 2026-08-17 / Local implementation coordinator.

- Decision: Preserve the connector's test-only fixed reuse clock fixture unchanged.
  Rationale: Its containment is clear, the exact selector and full module pass, and changing it would not make the production retention contract safer or smaller.
  Date/Author: 2026-08-17 / Local implementation coordinator.

- Decision: Treat strict process containment as defense in depth and block live public-target execution on the current same-account worker.
  Rationale: Job Objects and subreaping protect ordinary descendants, but they do not establish a separate OS identity, credential, Git configuration, or filesystem boundary. The implementation drains on unproven quiescence and skips target-path parsing, persistence, integrity subprocesses, and recursive cleanup; the required deployment boundary remains an operator-managed isolated account/container/VM/ACL setup.
  Date/Author: 2026-08-17 / Local implementation coordinator and independent adversarial review.

- Decision: Compile the two reviewed profiles into the existing registry/catalog surfaces, binding profile result-contract and resource-limit source data into only new manifest/reuse identities.
  Rationale: This retains old persistence/wire shapes and the three legacy hashes while ensuring parser thresholds, declared artifacts, retention ceilings, and result-affecting inputs invalidate new-profile reuse.
  Date/Author: 2026-08-17 / Local implementation coordinator.

- Decision: Publish the validated source to the existing draft PR for connector review while retaining the live-public-workload blocker.
  Rationale: The 2026-08-21 owner handoff explicitly authorizes logical commits and a normal push to the existing branch. Publication makes the implementation reviewable; it does not represent the same-account worker as safely isolated, authorize Industry live execution, or satisfy merge/release readiness.
  Date/Author: 2026-08-21 / Owner handoff and local implementation coordinator.

## Outcomes & Retrospective

The local implementation compiles two reviewed source profiles into the existing
trusted registry and catalog without moving legacy identities. The offline
validator reports exactly four public repositories and catalog digest
`8303bcc8c577557adccc7c299fc2816744f1c7a3c5f0f5ac39146d49c9643115`.
The new Industry and Zscripts manifest digests are respectively
`dfda235a1dda46fd144341e0105a9093396770698bf2a11c737bc7cfa5547ac6` and
`c449d97cc63bb9c28c293e4798a116261fb01ece55cc92407dd4a8a330d3107e`.

Synthetic production-path acceptance passed for Zscripts under Python 3.11,
Industry Resilience under Python 3.13, and the existing Accounting profile
under Python 3.12, each as exactly one passing JUnit case. The serial final
Python 3.11 suite passed `682` tests with `16` known platform/fixture skips;
the strict Playwright suite passed four cases with zero skips. The AST-scoped
hosted coverage gate measured `240/240` source-profile validation lines and
the catalog-readiness projection target remained above 90 percent. Native
Windows stress passed 20 cancellation and five full runner-module iterations;
WSL/Linux stress passed 30 cancellation and ten full runner-module iterations.
The final publication audit additionally passed 43 focused
profile/catalog/pnpm/capability tests and 16 native containment/finalization
tests with three explicitly Linux-only skips. All-files pre-commit, the offline
catalog validator, TODO policy, repository-wide diff check, Node syntax, full
action-SHA pin validation, detect-secrets, and bounded public-hygiene scanning
also passed on the final content.

Zscripts PR #119 is confirmed closed/merged at
`5fbb3a219d04ea3631042ef3a98272e1b5fca579`, so its live dogfood disposition
is TARGET-STATE-BLOCKED. Industry PR #130 is still open and draft at
`e3fea89db624414fe3cad7980768f0265cf9570a` as observed through GitHub at
`2026-08-22T00:56:48Z`; CI run `32536731040` and Docker Smoke run
`32536731320` succeeded on that exact head. The former `5e458da...` and
`01c4ebf...` values are historical. No operator-approved exact canonical checkout or separate OS
isolation boundary exists, so no controlled live execution was attempted. No
external repository, pull request, publication, branch, or source was mutated.

The implementation is authorized for normal publication to the existing draft
PR for connector review, with no claim of live-public-workload readiness. Live
execution remains **ENVIRONMENT-BLOCKED** until an operator provides a
least-privilege separate identity and a container/VM or equivalent OS-enforced
ACL/mount boundary. The final `pip-audit` advisory query also remains
environment-limited, and Docker is unavailable locally. Ultimate-head hosted
validation and connector review remain required before any merge decision.

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
