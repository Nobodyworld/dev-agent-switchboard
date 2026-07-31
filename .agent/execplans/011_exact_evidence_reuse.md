# Add exact evidence reuse with worker-local proof

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

Primary implementation issue: #121. Parent epic: #111. The exact-PR validation adapter was merged through PR #125 at `709b84dfe0dc101bdc79de562a95d1db713315f3`.

## Purpose / Big Picture

Avoid repeating deterministic validation when Switchboard already has successful evidence for exactly the same repository revision, trusted manifest, dependency inputs, worker environment, and result-affecting execution policy—and when the source worker can still prove that the marker-owned local evidence and declared artifacts remain present and unchanged.

The user-visible behavior is an explicit work-order reuse policy:

- `never`: always execute fresh; this remains the default and preserves all existing behavior.
- `allow_exact`: reuse only after exact identity matching and worker-local verification; otherwise execute fresh at most once while the same live lease remains owned.
- `require_exact`: never execute validation; succeed only after exact verified reuse and otherwise finish truthfully with a bounded non-success reason.

A successful reuse creates a distinct auditable run linked to the immutable source run and source evidence fingerprint. It does not copy, upload, mutate, extend, or delete source artifacts. Full logs and artifact bytes remain local.

## Progress

- [x] PR #125 squash-merged and issue #122 completed.
- [x] Exact implementation base selected: `709b84dfe0dc101bdc79de562a95d1db713315f3`.
- [x] Canonical branch `feat/exact-evidence-reuse` created from the exact base.
- [x] Initial living ExecPlan created.
- [x] Audit current work-order, run, evidence, worker, retention, startup-schema, and API contracts.
- [x] Run the untouched baseline dependency, server execution, and worker
  evidence suites.
- [x] Lock the versioned reuse-policy and reuse-identity contracts.
- [x] Implement additive persistence and restart-safe schema compatibility.
- [x] Implement exact successful-candidate lookup with deterministic ordering.
- [x] Implement worker-local retained-evidence verification without caller-controlled paths.
- [x] Integrate reuse selection, verification, fallback, and terminalization into the lease-owned execution flow.
- [x] Expose bounded provenance through normal work-order, run, and evidence APIs.
- [x] Complete focused identity, persistence, retention, concurrency,
  worker-verification, fallback, and API tests, including two independent
  database sessions and bounded API response assertions.
- [x] Add a fresh-first, locally verified second-run reuse proof plus changed
  local-result fallback and `require_exact` failure proofs.
- [x] Update API, architecture, configuration, and local-worker documentation.
- [x] Run complete local validation and record exact evidence.
- [x] Push the initial reviewed implementation and require the complete hosted
  PR matrix; head `2766d428b6917872fd5be0465baa2b2cd011e3f3` passed Commitlint
  run `30629772205` and CI run `30629772200`.
- [x] Correct connector review `4831588385`: reject mutually inconsistent
  source rows and make the Windows junction regression reach the filesystem
  reparse boundary.
- [x] Rerun the complete local correction matrix and preserve normal branch
  delivery through the existing draft PR.
- [x] Use the non-self-referential workflow-evidence convention: ultimate
  corrected-head workflow identifiers belong in PR #129's external review and
  merge record after that head exists, not in a commit that would create a new
  head.

## Surprises & Discoveries

- Observation: the existing `ExecutionEvidence` fingerprint deliberately includes run-specific values such as work-order ID, run ID, timestamps, durations, terminal outcome, cleanup state, steps, and artifact hashes.
  Evidence: `server/execution/evidence.py` canonicalizes the complete evidence document minus only the `fingerprint` field. Reuse therefore requires a separate canonical identity and must not weaken or repurpose the evidence fingerprint.

- Observation: worker-local storage already has strong marker, containment, regular-file, symlink/reparse, size, and streaming SHA-256 primitives, but the current `EvidenceStore` is constructed for a newly created run and verifies against in-memory creation metadata.
  Evidence: `client/python/execution_worker/evidence.py` provides `verify_ownership`, `finalize_artifacts`, and marker-safe pruning. Reuse needs a bounded safe reopen/verify operation that derives `run-<source_run_id>` beneath the configured evidence root and accepts no caller path.

- Observation: the execution service always assigns queued work by creating one active run and lease before the worker acts. This is the correct ownership boundary for `allow_exact` verification and fresh fallback.
  Evidence: `ExecutionService.checkout`, `create_active_run`, lease heartbeat, and `complete_run` already serialize one worker-owned attempt and reject stale completion.

- Observation: `ExecutionWorkOrder` and `ExecutionRun` currently have no reuse policy or provenance fields; `ExecutionRun.worker_id`, assignment times, and lease metadata are non-null.
  Evidence: `server/models.py`. Do not invent a sentinel worker to represent a server-only miss. Prefer a lease-owned verification attempt when a source worker exists, and make any no-candidate `require_exact` terminal model explicit and truthful if schema changes are necessary.

- Observation: the planning reference to
  `client/python/execution_worker/server_client.py` is stale; the bounded
  outbound protocol implementation is
  `client/python/execution_worker/client.py`.
  Evidence: the worker package contains `client.py`, and `worker.py` imports
  `ExecutionClient` from that module. No protocol layer is missing.

- Observation: the untouched baseline is green in the standalone task-only
  Python 3.11 environment required for Windows worker-child resolution.
  Evidence: dependency integrity passed; the server execution baseline
  produced `49 passed` in `27.92s`; the worker evidence/finalization/runtime
  baseline produced `25 passed, 1 skipped` in `42.91s`.

- Observation: strict worker response parsing exposed stale direct-test fixtures
  that omitted the newly server-derived reuse policy and execution-policy hash.
  Evidence: the first expanded regression run produced five fixture failures;
  updating the shared complete `WorkOrderOut` fixture restored the legacy matrix
  to `78 passed, 1 skipped` without making unknown response fields acceptable.

- Observation: the existing worker-smoke manifest retains no declared artifacts,
  so the lifecycle proof tampers with marker-bound `result.json`, while artifact
  byte, type, hash, and pruning-race cases are covered directly against the local
  verifier with a synthetic declared artifact.
  Evidence: the fresh-to-reused worker proof skips every validation step on a
  verified source; the tampered-result proof executes the trusted manifest once.

- Observation: hosted pre-commit sees only tracked files, while the final local
  pre-commit pass before the initial commits could not include the two then-new
  untracked test modules.
  Evidence: CI run `30629456819` passed Commitlint, secrets, links, security,
  typecheck, and tests but its lint job rejected the newly tracked fake-client
  constructor for six parameters. Removing the constructor-only test flag made
  pinned pre-commit pass without changing production code or coverage.

- Observation: exact candidate rows returned through a joined select can reuse
  stale identity-map objects after conditional lifecycle updates in the same
  database session.
  Evidence: adding final work-order status checks initially rejected legitimate
  same-session sources until the bounded candidate select used
  `populate_existing`. Candidate validation now evaluates authoritative joined
  state while retaining descending run-ID order and the 32-row bound.

- Observation: the previous Windows junction regression changed only candidate
  metadata, so marker-bound evidence validation rejected it before any
  filesystem lookup. A fully rebuilt evidence document, fingerprint, local
  result, and candidate reaches the junction-aware safe-path containment check
  and returns `source_artifact_unsafe`. The Windows test executes rather than
  skips; the POSIX symlink test remains unchanged.

- Observation: an initial correction-matrix attempt used a virtual environment
  whose Windows child interpreter resolved to a dependency-incomplete managed
  base installation. The already established standalone task-only Python 3.11
  environment resolved child commands correctly and passed the same
  server-backed smoke test and complete matrix. No repository dependency,
  manifest argv, or source change was justified.

## Decision Log

- Decision: preserve `never` as the default and require explicit opt-in for every other policy.
  Rationale: reuse changes execution semantics and must never be inferred from a branch, PR number, previous success, or approximate similarity.
  Date/Author: 2026-07-30 / owner and connector planning

- Decision: add a versioned `EvidenceReuseIdentity` separate from `ExecutionEvidence.fingerprint`.
  Rationale: the complete evidence fingerprint proves integrity of one run, while the reuse identity must include only deterministic equivalence inputs and exclude run-specific values.
  Date/Author: 2026-07-30 / connector planning

- Decision: database identity is only a candidate-selection mechanism; worker-local proof is mandatory before reuse success.
  Rationale: compact metadata cannot prove that retained bytes still exist, remain owned by the source worker, or have not changed.
  Date/Author: 2026-07-30 / owner and connector planning

- Decision: keep the outbound-worker architecture; do not add an inbound listener or general cache service.
  Rationale: the worker already polls the control plane and owns the local evidence root. Reuse verification should be a bounded assignment/disposition within that trust model.
  Date/Author: 2026-07-30 / connector planning

- Decision: under `allow_exact`, use the same live run/lease for local verification and at-most-once fresh fallback.
  Rationale: this preserves ownership, cancellation, heartbeat, stale-completion suppression, and worker capacity invariants without a second uncontrolled execution attempt.
  Date/Author: 2026-07-30 / connector planning

- Decision: never copy source evidence into the new run and never extend source retention because it was reused.
  Rationale: reuse is read-only provenance. Source evidence remains immutable and subject to its original retention policy.
  Date/Author: 2026-07-30 / owner and connector planning

- Decision: do not modify GitHub PR resolution/publication behavior in this slice.
  Rationale: PR #125 consumes normal run evidence. It may display fresh/reused provenance after the execution API gains it, but #121 must not broaden GitHub permissions, webhooks, workflow dispatch, or publication scope.
  Date/Author: 2026-07-30 / connector planning

- Decision: resolve reuse candidates only after the assigned worker checks out
  the exact SHA and derives its current environment and dependency-lock identity.
  The server then matches the complete identity and same source worker, and the
  worker performs local proof before any reused completion.
  Rationale: database metadata cannot predict or prove the current worker-local
  environment or retained bytes, and caller-selected source provenance is
  forbidden.
  Date/Author: 2026-07-31 / implementation

- Decision: order exact candidates by descending source run ID and scan at most
  32 exact database matches, accepting the newest structurally valid, unexpired,
  fresh source. Malformed matches are skipped closed rather than made reusable.
  Rationale: ordering is deterministic and bounded while permitting recovery
  from a newer corrupt metadata row without approximate matching.
  Date/Author: 2026-07-31 / implementation

- Decision: preserve rolling compatibility for `never` completions from
  pre-reuse workers. Such legacy evidence remains valid historical evidence but
  lacks a reuse identity and retention proof, so it cannot become a reuse source.
  Rationale: default fresh execution must remain compatible, while only new
  complete cryptographic identities may enter exact-candidate lookup.
  Date/Author: 2026-07-31 / implementation

- Decision: validate source work-order, run, evidence, identity, and fresh
  provenance consistency again after the bounded database lookup, and refresh
  joined ORM state from the database during that lookup.
  Rationale: indexed filters narrow candidates but cannot authenticate malformed
  or stale in-memory rows. Every inconsistent candidate must be skipped closed
  so an older valid exact source may still be selected.
  Date/Author: 2026-07-31 / connector review correction

- Decision: keep ultimate-head hosted workflow identifiers in PR #129's
  external review or merge record rather than embedding them in the same head.
  Rationale: committing identifiers for a completed workflow necessarily
  creates a newer, unvalidated head and an infinite documentation loop. The
  previous reviewed-head workflows remain useful historical evidence.
  Date/Author: 2026-07-31 / connector review correction

## Outcomes & Retrospective

The implementation and connector-review corrections are complete locally and
have been delivered through the existing branch workflow. Exact reuse is opt-in and maintains the
existing lease-owned outbound worker model: the worker derives current identity,
the server selects an exact same-worker candidate, and only marker-bound local
proof can produce a reused run. Source evidence remains immutable and retains
its original expiry. Legacy `never` callers and workers remain compatible but
cannot accidentally create reusable database-only evidence.

Connector review `4831588385` found two blockers on reviewed head
`2766d428b6917872fd5be0465baa2b2cd011e3f3`: incomplete final source-row
consistency and a Windows junction test that stopped at evidence identity. The
correction requires succeeded work-order/run state, terminal work-order timing,
fresh run and evidence provenance with no source linkage or retained candidate,
and authoritative joined-row refresh. Seven malformed-source variants now skip
to an older valid exact source, return unavailable when no valid source remains,
and remain unmodified. The rebuilt Windows junction fixture reaches safe-path
containment and returns the bounded unsafe-artifact disposition.

The complete corrected local matrix is green: required focused server coverage
produced `86 passed`; focused worker coverage produced `31 passed, 2 skipped`,
where the Windows junction test executed and the skips are its POSIX-only
counterparts. Full pytest produced `513 passed, 5 skipped`; strict browser
coverage produced `2 passed, 0 skipped`; aggregate configured coverage is 91%;
all 16 module thresholds passed. Dependency integrity, pre-commit, TODO policy,
Ruff, Black, Mypy, Bandit, pip-audit, Gitleaks, Lychee, and `git diff --check`
passed. The added-line public-hygiene audit found no workstation identity,
absolute local path, credential, private key, environment assignment, or
private-network URL.

Commitlint run `30629772205` and CI run `30629772200` are historical evidence
for reviewed head `2766d428b6917872fd5be0465baa2b2cd011e3f3`. Workflow
identifiers for the ultimate connector-corrected head are intentionally not
embedded here: they belong in PR #129's external review and merge record after
the corrected head exists.

## Context and Orientation

- `server/execution/evidence.py` defines strict complete evidence, environment identity, dependency-lock hashes, artifact records, and the complete evidence fingerprint.
- `client/python/execution_worker/evidence.py` owns evidence directories, `ownership.json`, artifact containment/type/size/hash verification, local `result.json`, and retention pruning.
- `server/models.py` defines `ExecutionWorkOrder`, `ExecutionRun`, `ExecutionLease`, workers, and manifests.
- `server/execution/entities.py` defines work-order drafts, checkout results, and worker completion payloads.
- `server/execution/service.py` owns approval, queueing, checkout, lease heartbeat, completion, evidence binding, and stale-lease recovery.
- `server/execution/repository.py` owns atomic persistence and conditional lifecycle transitions.
- `server/api/routers/execution.py` and the execution schemas expose operator and worker surfaces.
- `client/python/execution_worker/worker.py`, `runner.py`, `models.py`, and
  `client.py` implement the outbound worker loop and server protocol.
- `server/api/lifecycle.py` contains restart-safe additive startup compatibility used when `create_all()` cannot add columns to existing SQLite tables.
- `server/tests/test_execution_contracts.py`, `test_execution_evidence.py`, `test_execution_concurrency.py`, and worker evidence/runtime/finalization tests are the primary regression foundations.

## Plan of Work

1. Add a strict `ReusePolicy` enum with `never`, `allow_exact`, and `require_exact`. Extend caller-safe work-order creation with a reuse policy defaulting to `never`; reject unknown values and any caller-supplied source run, fingerprint, worker, path, artifact, or hash.

2. Define `EvidenceReuseIdentity` and canonical SHA-256 generation in `server/execution/evidence.py` or a focused adjacent module. At minimum bind schema/policy version, repository, exact SHA, manifest name/version/digest, canonical worker environment fingerprint, sorted dependency-lock path/hash pairs, result-affecting execution-policy identity, and parser/artifact declarations not already immutably bound by the manifest digest. Prove run IDs, work-order IDs, timestamps, durations, terminal reasons, cleanup text, evidence fingerprint, and source provenance do not affect it.

3. Extend persistence additively and minimally. Expected fields include work-order reuse policy; complete evidence reuse identity/hash; run provenance such as `reused_from_run_id`, source evidence fingerprint, reuse identity/hash, decision, and bounded reason code. Add indexes needed for exact successful candidate lookup. Use restart-safe additive startup DDL and compatibility tests; do not introduce a separate cache database or migration framework.

4. Add repository queries that select only structurally valid successful evidence matching the exact reuse identity. Require unexpired artifact retention, a known source worker, immutable source evidence fingerprint, and deterministic newest-or-oldest ordering documented in the plan. Treat malformed metadata, multiple ambiguous identities, missing fields, or inconsistent source/run/work-order records as ineligible.

5. Add a bounded server-derived reuse candidate to the worker assignment protocol. The worker must receive only source run ID, expected source worker ID, expected source evidence fingerprint, reuse identity/hash, retention metadata, and strict artifact records. It must not receive an absolute path or permit caller overrides.

6. Add worker-local verification that derives the source directory as `<configured evidence root>/run-<source_run_id>`, verifies the marker shape and exact worker/run/retention identity, rejects symlinks/junctions/reparse points/devices/traversal, revalidates each declared regular file's type and size, hashes it with before/after stability checks, verifies local `result.json` or other marker-bound source evidence identity as required, and returns only a bounded disposition/reason. Reuse must fail closed if pruning races verification.

7. Integrate the policy into the existing approved queue and live-lease lifecycle:
   - `never`: unchanged assignment and fresh execution.
   - `allow_exact`: verify an exact candidate on its source worker when possible; on verified success terminalize the new run as succeeded with provenance and without executing steps; on ineligible/failed verification, execute fresh at most once under the same still-live lease.
   - `require_exact`: never execute validation steps; verified candidate succeeds with provenance, otherwise terminalize truthfully with a bounded non-success reason. Do not create a sentinel worker. If a no-candidate result requires a schema adjustment for a non-executed run, make that model explicit, additive, and covered by API/concurrency tests.

8. Make selection, verification, fallback, pruning, completion, cancellation, lease expiry, and ownership loss race-safe. A stale worker must never finish a reuse or fallback result after lease ownership is lost or the server has already terminalized the order. Concurrent work orders may reuse one source run but must create distinct runs without mutating the source.

9. Expose compact provenance through existing APIs: reuse policy, decision, bounded reason code, reuse identity/hash, source run ID, and source evidence fingerprint. Never expose absolute paths, commands/argv, local artifact locations, environment dumps, full logs, secrets, or source artifact bytes.

10. Add focused and server-backed tests. The main proof should run one work order fresh, submit an equivalent second work order with `allow_exact`, locally reverify the first run, and complete the second without validation execution. Changed SHA, manifest digest, lock hash, environment fingerprint, parser/artifact policy, expired retention, changed bytes, missing marker, wrong worker, and malformed metadata must cause fresh fallback or `require_exact` failure as specified.

11. Update `docs/API.md`, `docs/architecture/local-execution-broker.md`, `docs/configuration.md`, `docs/operations/local-worker.md`, and any execution/GitHub integration documentation needed to explain policy, provenance, local verification, failure reasons, retention behavior, and non-goals.

12. Run the focused suites and complete protected matrix, remove generated artifacts, audit public content, commit intentionally, push only `feat/exact-evidence-reuse`, and keep the PR draft until connector review is complete.

## Concrete Steps

Verify the exact starting state:

```bash
git fetch origin --prune --tags
git worktree list --porcelain
git rev-parse origin/main
git rev-parse origin/feat/exact-evidence-reuse
git merge-base origin/main origin/feat/exact-evidence-reuse
git status --short --branch
```

The exact initial identities are:

```text
origin/main and merge base:
709b84dfe0dc101bdc79de562a95d1db713315f3

origin/feat/exact-evidence-reuse:
7838fbff7875ee455085626ba02f625e964c61c2
```

Use a clean isolated worktree for the existing branch. Stop rather than resetting, rebasing, force-pushing, cleaning uncertain files, or disturbing another worktree.

Before implementation run the existing foundations:

```bash
python -m pip check
python -m pytest -q -p no:cacheprovider \
  server/tests/test_execution_contracts.py \
  server/tests/test_execution_evidence.py \
  server/tests/test_execution_concurrency.py
python -m pytest -q -p no:cacheprovider \
  client/python/tests/test_execution_worker_evidence.py \
  client/python/tests/test_execution_worker_finalization.py \
  client/python/tests/test_execution_worker_runtime.py \
  client/python/tests/test_execution_worker_server_smoke.py
```

During implementation add focused tests for reuse identity, schema compatibility, candidate selection, worker verification, retention races, lease loss, fallback-at-most-once, and API redaction. Automated tests must not require live GitHub credentials or external network access.

Final validation must include:

```bash
python -m pip check
python -m pre_commit run --all-files --show-diff-on-failure
python scripts/dev.py check-todos --root .
python -m ruff check server client scripts tests web switchboard_cli.py switchboard_client.py
python -m black --check server client scripts tests web switchboard_cli.py switchboard_client.py
python -m mypy --config-file mypy.ini server client scripts

mkdir -p reports
python -m pytest --maxfail=1 --disable-warnings --junitxml=reports/pytest.xml
SWITCHBOARD_STRICT_PLAYWRIGHT=1 python -m pytest web/tests/test_ui.py -rA

python -m pytest \
  --cov=server/extensions \
  --cov=server.application.task_service \
  --cov=server.observability \
  --cov=server.application.configuration_service \
  --cov-report=term-missing \
  --cov-report=json:reports/coverage.json

python scripts/dev.py coverage-gate --json reports/coverage.json \
  --module server/extensions/contracts.py=85 \
  --module server/extensions/interfaces.py=85 \
  --module server/extensions/loader.py=85 \
  --module server/extensions/runtime.py=85 \
  --module server/extensions/builtin/task_metrics.py=85 \
  --module server/extensions/builtin/plan_metrics.py=85 \
  --module server/extensions/builtin/plan_latency.py=80 \
  --module server/extensions/builtin/plan_snapshot.py=80 \
  --module server/extensions/builtin/activity_feed.py=85 \
  --module server/extensions/observability.py=80 \
  --module server/observability/diagnostics.py=80 \
  --module server/observability/health.py=85 \
  --module server/observability/activity.py=80 \
  --module server/observability/overview.py=85 \
  --module server/application/task_service.py=75 \
  --module server/application/configuration_service.py=85

python -m bandit -q -r server -x server/tests
python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
gitleaks detect --verbose
mkdir -p lychee
lychee --config lychee.toml --no-progress \
  README.md CHANGELOG.md SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md \
  "docs/**/*.md" --exclude-path docs/history --exclude-path archive
git diff --check
git status --short --branch --untracked-files=all
```

Remove JUnit, coverage, Lychee, browser, database, cache, bytecode, and other generated artifacts before staging.

## Validation and Acceptance

Acceptance requires all of the following:

- `never` is the default and existing fresh execution behavior remains unchanged.
- Reuse identity is canonical, versioned, deterministic, and excludes run-specific values.
- Exact input changes invalidate reuse; fuzzy or approximate matching is impossible.
- Database matches cannot produce success without source-worker local proof.
- Worker verification accepts no caller-controlled path and safely rejects traversal, symlink, junction/reparse, device, marker, ownership, type, size, hash, retention, and race failures.
- Successful reuse creates a distinct auditable run linked to immutable source evidence without executing validation steps or copying artifact bytes.
- Multiple work orders may reuse one source run without source mutation.
- `allow_exact` falls back fresh at most once and only while the same lease remains live and owned.
- `require_exact` never executes validation.
- Ownership loss, cancellation, lease expiry, retention pruning, or server-terminal state suppress stale completion.
- APIs expose compact provenance and no sensitive/local-only data.
- The server-backed fresh-then-reuse proof passes, and changed identity/environment/bytes produce the specified fallback or non-success result.
- Complete local and hosted protected validation passes.

## Idempotence and Recovery

- Recreate an uncertain worktree rather than cleaning it.
- Never reset, rebase, or force-push the canonical branch.
- Additive schema compatibility must be restart-safe and harmless when columns/indexes already exist.
- Repeating candidate lookup or local verification must not mutate source evidence.
- Retrying a verification disposition must be conditionally fenced by current lease/run/work-order state.
- A failed `allow_exact` verification may transition to fresh execution only once; retries must not launch a second fresh execution.
- Generated validation outputs may be deleted and recreated safely.
- If a trust-boundary or product-behavior conflict appears, preserve evidence and stop for review rather than weakening checks.

## Artifacts and Notes

Record during implementation:

- exact starting SHAs: main and merge base
  `709b84dfe0dc101bdc79de562a95d1db713315f3`; branch
  `7838fbff7875ee455085626ba02f625e964c61c2`;
- untouched baseline: `python -m pip check` passed; server execution suites
  produced `49 passed` in `27.92s`; worker evidence/finalization/runtime suites
  produced `25 passed, 1 skipped` in `42.91s`;
- expanded legacy regression after the response-fixture compatibility correction:
  `78 passed, 1 skipped` in `75.95s`;
- direct identity and server selection/lifecycle checkpoint: `50 passed` in
  `27.47s`;
- worker-local proof and lifecycle checkpoint: `19 passed, 2 skipped` in
  `10.51s`; the skips are intentional opposite-platform symlink/junction
  counterparts;
- persistence additions: work orders retain `reuse_policy` and
  `execution_policy_hash`; runs retain strict identity/hash, decision/reason,
  source run/fingerprint, bounded active candidate metadata, and evidence
  retention expiry. Exact lookup is indexed by identity hash, worker, and status;
  source-run and retention indexes support provenance and expiry inspection;
- complete focused actor-independent reuse matrix after concurrency, startup,
  API, and verifier-bound coverage: `118 passed, 2 skipped` in `74.72s`;
- final full pytest: `506 passed, 5 skipped` in `293.89s`; strict browser: `2
  passed, 0 skipped` in `8.28s`;
- aggregate configured coverage: 91%. Module results: contracts 95.40%,
  interfaces 94.17%, loader 100.00%, runtime 100.00%, task metrics 92.59%,
  plan metrics 95.00%, plan latency 87.76%, plan snapshot 100.00%, activity
  feed 100.00%, extension observability 97.73%, diagnostics 90.16%, health
  95.78%, activity 94.83%, overview 100.00%, task service 79.23%, and
  configuration service 91.30%;
- final local gates: pip check, pre-commit, TODO policy, Ruff, Black, Mypy,
  Bandit, pip-audit, Gitleaks, Lychee, and diff check passed. Gitleaks scanned
  232 commits with no leaks; pip-audit found no known vulnerabilities;
- public hygiene: added lines and new files contain no workstation identity,
  absolute local path, credential-shaped value, private key, environment
  assignment, or private-network URL. Generated reports, databases, link state,
  coverage data, caches, and bytecode were removed before staging;
- initial pushed evidence head `b1cca75e5052de3f795b9b8530d3662ad0512dd3`
  reached CI run `30629456819`; a test-only Ruff arity failure required one
  correction commit, so that run is historical rather than final evidence;
- reviewed implementation head `2766d428b6917872fd5be0465baa2b2cd011e3f3`
  passed Commitlint run `30629772205` and CI run `30629772200`; these are
  historical reviewed-head results, while ultimate correction-head workflow
  identifiers remain in PR #129's external record;
- connector review `4831588385` correction checkpoint: direct blocker
  regressions produced `8 passed`; required focused server suites produced `86
  passed` in `49.59s`; required focused worker suites produced `31 passed, 2
  skipped` in `21.25s`, with the Windows junction proof executed;
- corrected full pytest: `513 passed, 5 skipped` in `434.06s`; strict browser:
  `2 passed, 0 skipped` in `9.78s`;
- corrected configured coverage: `513 passed, 5 skipped` with 91% aggregate;
  all 16 module percentages remained unchanged and above threshold;
- corrected security and public gates: Bandit passed; pip-audit found no known
  vulnerabilities; Gitleaks scanned 236 commits and approximately 4.54 MB with
  no leaks; Lychee passed with two informational redirects;
- schema fields/indexes and startup compatibility behavior;
- canonical reuse-identity example with sensitive values absent;
- focused identity and malformed-input counts;
- worker verification results for success and every rejected path/type/marker/hash/retention case;
- race and lease-loss results;
- first-fresh/second-reused server-backed proof;
- changed-input fallback and `require_exact` failure proof;
- full pytest, strict browser, coverage, quality, security, dependency, secret, and link results;
- final hosted Commitlint and CI identifiers;
- public-hygiene and clean-tree proof.

## Interfaces and Dependencies

Expected focused interfaces include equivalents of:

- `ReusePolicy` with `never`, `allow_exact`, and `require_exact`.
- `EvidenceReuseIdentity` plus canonical JSON/hash helpers.
- server-owned `ReuseCandidate` containing no local path.
- bounded worker assignment metadata for local verification.
- `ReuseVerificationDisposition` with success/failure and a bounded reason code.
- repository methods for exact successful candidate lookup and conditional reuse/fallback completion.
- run provenance fields including source run and source evidence fingerprint.
- compact API schemas for policy and provenance.
- worker evidence helpers that reopen and verify only marker-owned `run-<id>` directories beneath the configured evidence root.

Use the standard library and existing SQLAlchemy/Pydantic stack unless a new dependency is demonstrably necessary. Any new dependency requires a separate justification, pinning, audit, and documentation update.
