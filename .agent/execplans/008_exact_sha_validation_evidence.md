# Add exact-SHA validation evidence

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

Primary implementation issue: #114. Parent epic: #111. The execution control plane was completed in #112 and the pull-based trusted local worker was completed in #113.

## Purpose / Big Picture

Switchboard can now assign an approved work order to a trusted outbound-only local worker, create a disposable exact-SHA Git worktree, execute immutable fixed-argv manifest steps, maintain ownership heartbeats, retain local logs, report bounded results, and clean up safely.

The next user-visible milestone is a complete deterministic validation workflow. An operator should be able to approve one `validate-switchboard@1` work order for one exact commit SHA, let the local worker execute the reviewed read-only validation steps, and retrieve compact evidence through the Switchboard API without paying a coding agent merely to run tests, coverage, or security checks.

The compact evidence must identify exactly what was tested, where the trusted execution definition came from, which worker environment ran it, what each step reported, what local artifacts were retained, and whether cleanup succeeded. Full logs remain local under a worker-owned evidence root. API responses expose only strict bounded summaries, safe relative references, hashes, retention metadata, and a deterministic fingerprint.

## Progress

- [x] Execution control plane merged in PR #116.
- [x] Pull-based trusted local worker merged in PR #119 at `f549ab7bb2efc274dc2d79e12502d5653ddc8886`.
- [x] Issue #114 unblocked and rewritten with locked Phase 1B boundaries.
- [x] Canonical branch `feat/exact-sha-validation-evidence` created from exact base `f549ab7bb2efc274dc2d79e12502d5653ddc8886`.
- [x] Existing completion placeholders, execution-run JSON columns, manifest registry, worker result handling, and application configuration entry points inspected.
- [x] Reproduced the hosted pinned-hook failure locally; retained the exact formatter-only mutation and reran all hooks successfully.
- [x] Re-ran cancellation-precedence, monitor, and runtime regressions after normalization (3 + 12 + 6 tests passed).
- [x] Define strict versioned artifact and compact evidence models.
- [x] Add the trusted `validate-switchboard@1` manifest and immutable safe metadata.
- [x] Add a worker-owned evidence-directory lifecycle separate from the disposable source worktree.
- [x] Add artifact validation, hashing, redaction metadata, and retention expiry.
- [x] Add deterministic evidence fingerprinting from canonical JSON.
- [x] Extend worker step results with timestamps and declared parsed result kinds.
- [x] Complete runs with strict evidence and artifact metadata.
- [x] Add `GET /api/execution/runs/{run_id}/evidence`.
- [x] Add marker-verified retention cleanup for expired evidence directories.
- [x] Add focused security, schema, fingerprint, parser, retention, and API tests.
- [x] Add two server-backed exact-SHA end-to-end executions against temporary repositories.
- [x] Update operator and API documentation.
- [x] Run the complete local repository validation and record environment limitations.
- [x] Run the complete repository validation and protected hosted matrix.
- [x] Record final evidence, limitations, and draft/unmerged handoff state here.
- [x] Reproduce the connector-review gap with direct malformed-worker payloads that bypass worker redaction.
- [x] Add a shared server-owned absolute-local-path policy at the execution schema boundary.
- [x] Reject absolute local paths recursively in compact evidence and in persisted completion/run text.
- [x] Add direct Windows, POSIX, UNC, `file:` URI, safe-relative, safe-URI, persistence, and fail-closed API regressions.
- [x] Re-run the complete focused and repository validation after the connector correction.
- [x] Record the final hosted exact-SHA workflow IDs and draft PR handoff state after the connector correction.

## Surprises & Discoveries

- Observation: the control plane already persists `artifact_metadata` and `evidence_metadata` as JSON on `ExecutionRun` and returns them through `ExecutionRunOut`.
  Evidence: `server/models.py` defines the two JSON columns and `server/execution/schemas.py` currently exposes them as untyped `list[dict[str, Any]]` and `dict[str, Any]` placeholders.

- Observation: the completion endpoint already accepts bounded result summaries plus artifact and evidence metadata, so the first useful evidence workflow does not require a new upload endpoint or a new database table.
  Evidence: `ExecutionCompletionIn` includes `result_summary`, `artifact_metadata`, and `evidence_metadata`, and `ExecutionClient.complete_run()` already sends those fields.

- Observation: full logs are already retained beneath a worker-owned run directory after source-worktree cleanup.
  Evidence: the #113 worker writes stdout, stderr, and `result.json` beneath its owned run directory and removes only the disposable Git worktree.

- Observation: `AppConfig` currently configures only API/UI concerns; worker filesystem policy belongs in `WorkerConfig` and CLI configuration rather than the FastAPI application factory.
  Evidence: `server/api/__init__.py` contains title, version, CORS, UI, static-directory, and lifespan settings only, while `client/python/execution_worker/config.py` owns worker roots, repository mappings, limits, and runtime policy.

- Observation: the existing trusted manifest registry already includes private executable steps in the digest and exposes only safe metadata through the API.
  Evidence: #113 added `TrustedStep`, private fixed argv, environment additions, and digest-bound execution definitions while `CommandManifestOut` remains metadata-only.

- Observation: the first planning commit initially failed `end-of-file-fixer` because the new ExecPlan lacked the normalized final newline; the follow-up `docs(evidence): normalize ExecPlan file` retained that hook output.
  Evidence: branch commits `6a25b7e` and `ed487e1` record the initial document and exact EOF normalization.

- Observation: hosted validation exposed an ownership-loss/process-termination race: a heartbeat could establish authoritative cancellation while process-tree termination raised locally, allowing the outer generic error path to replace cancellation with `worker_error:RuntimeError` and attempt a stale completion.
  Evidence: commits `92c9834` through `deedf93` and `client/python/tests/test_execution_worker_cancellation_precedence.py` cover ownership loss, server-terminal state, and ordinary runner exceptions.

- Observation: the exact pinned local pre-commit mutation was limited to wrapping two 92-character `_cancellation_outcome(token)` assignments in `client/python/execution_worker/worker.py`; the second all-files run passed with no further changes.
  Evidence: local `python -m pre_commit run --all-files --show-diff-on-failure` failed only Ruff E501/Ruff format on worker lines 454 and 460, then passed after retaining the six-line formatter output in commit `892a3ef`.

- Observation: pytest currently emits a cache warning because `.pytest_cache/v/cache` cannot be created over an existing local path, but the required worker regressions complete successfully using system temporary repositories.
  Evidence: cancellation-precedence reported 3 passed, monitor 12 passed, and runtime 6 passed; each reported only `PytestCacheWarning` for the repository cache path.

- Observation: the operator's shared Python environment has an unrelated `opencv-python 4.12.0.88` / `numpy 2.3.4` dependency conflict, so `python -m pip check` is truthful diagnostic evidence rather than a required validation gate inside the trusted manifest.
  Evidence: the first server-backed validation failed only at dependency health; making that declared step diagnostic-only allowed the required repository checks to determine the terminal outcome while preserving the failed dependency audit.

- Observation: a direct ORM-created active run exposed that the migration-free implementation must preserve the existing non-null `{}` database sentinel for absent evidence rather than introduce a nullable column that existing #112 databases do not have.
  Evidence: the focused concurrency invariant initially failed with `NOT NULL constraint failed: execution_runs.evidence_metadata`; restoring `nullable=False, default=dict`, explicitly persisting `{}`, and normalizing that sentinel to API `null` preserved the deployed schema. Persistence, startup, and strict schema tests then passed (19 tests), while the evidence endpoint returns 404 for absent evidence and 500 for a nonempty malformed record.

- Observation: tool output may contain absolute installation paths even when argv and environment metadata are safe.
  Evidence: the dependency diagnostic exposed a local site-packages path; bounded API summaries now redact Windows and POSIX absolute paths, with runner and server-backed API assertions covering the boundary.

- Observation: the first hosted Python 3.11 run rejected the POSIX symlink fixture with the safe message `evidence path escaped its owned run directory`, while the test regex accepted only `symlink|reparse`.
  Evidence: CI run `29883368990` failed only that assertion. Commit `946a7e9` broadened the assertion to the already-supported `escaped` rejection; final CI run `29883500759` then passed every job.

- Observation: worker-side summary redaction protected the normal execution path but was not an authoritative server contract; an authenticated malformed worker could submit absolute local paths directly in nested evidence summaries, terminal text, or `result_summary` and have them persisted.
  Evidence: connector review of `ExecutionEvidence`, `ExecutionCompletionIn`, and `ExecutionRunOut` found strict relative artifact validation but no shared free-text path policy. New raw-payload regressions recompute an otherwise-valid evidence fingerprint after inserting Windows or POSIX local paths and prove the request is rejected with HTTP 422 before the run changes.

- Observation: JSON serialization doubles relative Windows separators, so an initial UNC detector treated the interior `\\` in an encoded `server\sample.py` coverage row as a network-root prefix and rejected the normal two-run proof.
  Evidence: the first focused worker rerun returned HTTP 422 despite all local paths being redacted. Requiring a true non-alphanumeric token boundary for UNC roots and adding a JSON-encoded relative-Windows-path regression restored the two-run proof without weakening drive, UNC, POSIX, or `file:` rejection.

- Observation: the first complete instrumented coverage run had one transient Windows scheduling failure when the ownership-loss cancellation test took 12.2 seconds against its 5-second assertion; the same test had already passed in focused and full uninstrumented suites.
  Evidence: the exact test passed under identical coverage instrumentation in 2.63 seconds, and the unchanged complete coverage command then passed 383 tests with 4 skips in 277.00 seconds at 93% aggregate coverage. No cancellation code or timing limit was changed.

## Decision Log

- Decision: implement `validate-switchboard@1` as the first complete evidence manifest.
  Rationale: the first workflow should validate the repository that owns and reviews the manifest. This gives deterministic fixed commands and meaningful end-to-end evidence without prematurely creating a general repository-profile language.
  Date/Author: 2026-07-21 / ChatGPT connector planning

- Decision: keep full artifact bytes local under a worker-configured evidence root and store only strict compact metadata in the server.
  Rationale: artifact upload/download would add transport, authentication, size, retention, and secret-exfiltration risks beyond #114. Connector review needs hashes and bounded summaries, not remote access to full local logs.
  Date/Author: 2026-07-21 / ChatGPT connector planning

- Decision: use one marked evidence directory per execution run, separate from the disposable source worktree.
  Rationale: source cleanup and evidence retention have different lifecycles. The worker must be able to remove the source checkout immediately while retaining logs and reports until their configured expiry.
  Date/Author: 2026-07-21 / ChatGPT connector planning

- Decision: preserve the existing `ExecutionRun.artifact_metadata` and `ExecutionRun.evidence_metadata` JSON columns but replace API and worker placeholders with strict versioned models.
  Rationale: the current persistence shape is sufficient for compact evidence. Avoiding a migration reduces risk and keeps #114 focused on validation correctness rather than schema expansion.
  Date/Author: 2026-07-21 / ChatGPT connector planning

- Decision: add `GET /api/execution/runs/{run_id}/evidence` as a compact read-only projection.
  Rationale: callers should not parse generic execution-run placeholders or full result-summary strings to retrieve evidence. A dedicated response can enforce versioning, bounds, and omission of full logs and absolute paths.
  Date/Author: 2026-07-21 / ChatGPT connector planning

- Decision: compute the evidence fingerprint from canonical JSON using sorted keys, compact separators, UTF-8, and SHA-256.
  Rationale: a deterministic documented encoding is required before later evidence-reuse work can safely compare records across runs.
  Date/Author: 2026-07-21 / ChatGPT connector planning

- Decision: implement deterministic retention expiry and a marker-verified prune helper, but do not add a background scheduler in #114.
  Rationale: retention behavior can be proven through startup/idle maintenance or an explicit worker maintenance call. A separate scheduler is unnecessary for the first end-to-end evidence contract.
  Date/Author: 2026-07-21 / ChatGPT connector planning

- Decision: authoritative cancellation continues to outrank a simultaneous local runner or process-tree termination exception.
  Rationale: ownership loss and server-terminal state are facts established by the control plane; emitting a local failed completion after either fact is stale and unsafe. Overall timeout remains `timed_out`, other owned cancellation remains `cancelled`, and an ordinary uncancelled runner exception remains a failed completion.
  Date/Author: 2026-07-21 / Codex implementation

- Decision: keep raw local command logs explicitly marked `redaction_state: none` while redacting compact API summaries.
  Rationale: local evidence is operator-private diagnostic material and must remain faithful for audit; the API boundary must not expose full logs, absolute paths, secrets, or arbitrary environment values.
  Date/Author: 2026-07-21 / Codex implementation

- Decision: enforce one server-owned absolute-local-path policy in `server/execution/text_policy.py`, independently of the worker's redaction regex.
  Rationale: execution request schemas now recursively reject drive-rooted Windows paths, UNC paths, POSIX-rooted paths, and local `file:` URIs before persistence; common non-local URI schemes and strict relative artifact/log references remain deliberate accepted forms. Evidence models apply the same recursive check to every nested string, and run/work-order response schemas revalidate persisted terminal text so corrupt or legacy rows fail closed instead of leaking through normal APIs.
  Date/Author: 2026-07-22 / Codex implementation

## Outcomes & Retrospective

Implementation and complete local validation are complete pending the final hosted matrix.

- Connector correction focused validation: `python -m pytest -q -p no:cacheprovider server/tests/test_execution_evidence.py server/tests/test_execution_contracts.py` passed 45 tests with 8 pre-existing SQLAlchemy `datetime.utcnow` deprecation warnings. Focused Ruff and Black checks passed for the five changed Python files. The direct API regressions prove malformed completion requests do not consume the active lease or persist result/evidence text, `/api/execution/runs` fails closed for corrupt persisted run text, and `/api/execution/runs/{run_id}/evidence` returns an explicit server failure for corrupt persisted evidence even when the attacker recomputes the canonical fingerprint.
- Connector correction worker and ownership validation: the final worker evidence/finalization/runner/server-backed suite passed 23 tests with one expected POSIX-only symlink skip in 76.57 seconds; the cancellation-precedence, monitor, runtime, client, and execution-concurrency suite passed 26 tests in 26.56 seconds. The normal two-run exact-SHA server-backed proof passed after the UNC-boundary correction, retaining the earlier successful hosted-workflow evidence for exact SHAs `3a8422b70e15133be064094e46358c22a661a929` and `1bb9bc24daadd3d46064323a76a25ff353b6ea65`.
- Connector correction complete local validation: the exact pinned all-files pre-commit command passed with the new helper staged and included; standalone Ruff passed; standalone Black passed (the pinned all-files hooks formatted and checked the full tracked Python set); Mypy passed 162 source files; TODO metadata passed; final full pytest passed 384 tests with 4 skips and 349 existing deprecation warnings in 314.14 seconds; the final instrumented run passed the same 384/4 result at 93% aggregate coverage in 311.38 seconds; all 16 configured coverage thresholds passed, with the lowest `plan_latency.py` result at 87.76% against 80%; strict Playwright passed 2 tests with zero skips in 37.10 seconds.
- Connector correction security and documentation validation: isolated CPython 3.11 Bandit 1.8.6 passed; `pip-audit` reported no known vulnerabilities after one network-bound timeout and a successful unchanged retry; Gitleaks scanned 203 commits and found no leaks; Lychee passed on an unchanged retry after four external URLs initially timed out, with two redirect hints and no errors. `git diff --check` passed.
- The known non-gating shared-interpreter `python -m pip check` diagnostic remains unchanged: `opencv-python 4.12.0.88` requires `numpy<2.3.0,>=2` while NumPy 2.3.4 is installed, and the CPython 3.14 environment reports an invalid `~andit` distribution. Dependencies were not changed.
- Connector correction hosted validation: exact code-bearing SHA `b6274bd8f43f6df5504d5787f1bb3e418ff518e7` passed Commitlint run `29901308518` and CI run `29901308554`. CI passed lint, typecheck, pytest, security, link check, secrets audit, coverage, and strict browser jobs. Its only annotations were GitHub's Node 20 action-deprecation notices, unrelated to issue #114. PR #120 remained open, draft, and unmerged after both workflows completed.

- `validate-switchboard@1` currently resolves to manifest digest `10e99418e4e6f0e9f4a6e95fb5b9a267dab4eeac4671cf58533c8b9afe1fed98`; every executable field, parser declaration, artifact declaration, fixed environment value, and dependency-lock path participates in the digest.
- Evidence and artifact schema version 1 use strict Pydantic models. The fingerprint is SHA-256 over UTF-8 JSON with sorted keys, compact separators, `ensure_ascii=False`, and the `fingerprint` field omitted.
- The worker-owned marker records schema version, worker/run identity, creation, and expiry. Source worktrees are removed immediately; marked local evidence is retained for the configured 1--3,650 day period within count and byte limits.
- Supported parsed kinds are pytest counts, coverage, combined pytest/coverage, Bandit security audit, and dependency audit. Parser failure is recorded as `parser_failed` without fabricating results or changing a successful process exit by itself.
- The exact blocked evidence/worker command passed after final adjustments with 31 passed and one expected POSIX-only symlink skip in 14.83 seconds. The full focused execution-worker/server-execution set passed with exit 0 in 141.4 seconds before the final migration-free sentinel regression was added; the affected persistence/startup/schema subset then passed 19 tests and the two-run server-backed evidence test passed again.
- The required server-backed validation completed twice against temporary repositories and returned retrievable compact evidence for exact SHAs `3a8422b70e15133be064094e46358c22a661a929` and `1bb9bc24daadd3d46064323a76a25ff353b6ea65`. Both runs verified the detached SHA, artifact hashes, retained logs, source cleanup, canonical checkout integrity, and API redaction boundaries.
- Known local limitations are the operator environment's pre-existing `opencv-python`/`numpy` `pip check` conflict and the unreadable repository `.pytest_cache/v/cache` path warning. `worker_restricted` remains an operator-controlled network posture, not per-process firewall isolation.
- Complete local validation: pre-commit passed every hook; TODO metadata, standalone Ruff, Black, and Mypy (161 source files) passed; final full pytest reported 367 passed and 4 skipped; strict Playwright reported 2 passed with no skips; the instrumented suite before the final sentinel-only regression reported 366 passed and 4 skipped with 93% aggregate measured coverage; every configured module threshold passed (lowest measured configured module: 87.76% against an 80% threshold).
- Security and documentation validation: Bandit 1.8.6 passed under isolated CPython 3.11, matching CI. The shared CPython 3.14 installation cannot produce a valid Bandit scan because Bandit accesses the removed `ast.Constant.s` attribute, and its CLI shim is missing due to an invalid `~andit` distribution. `pip-audit` found no known vulnerabilities, Gitleaks found no leaks across 199 commits, and Lychee passed with two redirect hints.
- `python -m pip check` remains the sole non-passing local command because of the external `opencv-python 4.12.0.88` requirement `numpy<2.3.0,>=2` versus installed `numpy 2.3.4`; it also reports the invalid `~andit` distribution. Repository-required validation itself is covered by the passing isolated scanner and hosted Python 3.11 matrix.
- Hosted validation for implementation/test head `946a7e9b65c18c7c4f621eac51dea460e14484e6` passed in CI run `29883500759`: link check, lint, typecheck, test, security, secrets audit, strict browser UI, and coverage all concluded `success`. Commitlint run `29883500819` also concluded `success`.
- PR #120 remained open, draft, cleanly mergeable, and unmerged at handoff. Issue #104, releases, branch history, and `main` were not modified.

Deferred scope remains evidence reuse, GitHub integration, cost routing, MCP, RPA, artifact upload/download, and per-worker credentials.

Completion evidence includes:

- final manifest identity and digest behavior;
- evidence-root configuration and ownership marker format;
- strict artifact/evidence schema versions;
- exact fingerprint canonicalization inputs;
- supported parsed result kinds and truthful unsupported cases;
- two end-to-end run IDs and tested SHAs;
- artifact hashes, retention evidence, and cleanup results;
- full local and hosted validation counts;
- limitations deferred to evidence reuse, GitHub integration, cost routing, MCP, and RPA issues.

## Context and Orientation

The main implementation surfaces are:

- `server/execution/registry.py` — trusted manifest and immutable step definitions. Add `validate-switchboard@1` here or in a focused registry module imported here; do not load executable definitions from caller-controlled YAML.
- `server/execution/schemas.py` — strict API input/output contracts. Replace untyped completion metadata placeholders with strict evidence models and add the compact evidence response.
- `server/models.py` — `ExecutionRun` already has `artifact_metadata` and `evidence_metadata` JSON columns. Prefer these columns unless implementation proves they cannot safely hold the strict contract.
- `server/execution/repository.py` and the execution service — persist terminal results and retrieve joined work-order/run evidence safely.
- `server/api/routers/execution.py` — existing manifest, work-order, worker, checkout, heartbeat, completion, and run endpoints. Add the read-only compact evidence route here.
- `client/python/execution_worker/config.py` — worker filesystem roots and limits. Add evidence-root, retention, artifact-count, per-artifact-size, and total-evidence-size policy here.
- `client/python/execution_worker/worktree.py` — exact-SHA disposable source lifecycle. Do not overload this module with retained evidence deletion; create a separate focused evidence-storage helper.
- `client/python/execution_worker/runner.py` — fixed process execution and bounded step results. Extend result timing and parsing without allowing caller-controlled commands.
- `client/python/execution_worker/worker.py` — orchestrates checkout, validation, monitoring, source cleanup, local record writing, and completion. Integrate evidence finalization after all step output is closed and before completion.
- `scripts/local_worker.py` — reads operator configuration and starts the worker. Wire new evidence policy without accepting secrets or arbitrary paths from work orders.
- `docs/operations/local-worker.md` — explain evidence-root ownership, retention, disk limits, privacy, and compact API behavior.
- `client/python/tests/` and `server/tests/` — existing temporary-repository, ASGI, worker, and manifest fixtures should be reused rather than replaced.

The current local worker retains complete stdout and stderr logs and reports bounded summaries. The evidence implementation should build on that behavior rather than create a second process runner.

## Plan of Work

1. Define strict evidence models.

   Add versioned Pydantic models for artifacts, per-step evidence, parsed test/coverage/security summaries, environment identity, and the complete compact evidence document. Forbid unknown fields. Bound strings, lists, numbers, timestamps, media types, and hashes. Require lowercase 64-character SHA-256 values. Reject absolute paths, traversal, separators that escape the run directory, and executable-shaped keys.

   `ExecutionCompletionIn` should accept the strict models rather than arbitrary dictionaries. `ExecutionRunOut` may continue to expose persisted data, but the dedicated evidence endpoint must validate persisted JSON against the strict response contract and fail explicitly if stored data is malformed.

2. Add `validate-switchboard@1`.

   Define a narrow ordered set of reviewed read-only validation steps using immutable argv and current repository commands. Keep commands cross-platform where practical by using Python module entry points rather than shell syntax. Each step declares a safe ID, title, timeout, output limit, required/diagnostic status, artifact declarations, and optional parser kind.

   The manifest should cover a useful but bounded validation profile. It may include pinned pre-commit, Mypy, pytest, the current coverage command and coverage gate, security checks, and `git diff --check` only when those tools and commands are already supported by the repository. Do not add Docker, browser installation, GitHub calls, or dependency installation merely to enlarge the first proof. Capability requirements must truthfully express what the chosen fixed steps need.

3. Create the evidence-directory lifecycle.

   Add a focused module such as `client/python/execution_worker/evidence.py`. It should create exactly one run-owned directory under the configured evidence root, write an ownership marker containing schema version, worker ID, run ID, and creation time, create contained `logs/` and `artifacts/` directories, and reject overlap with repository roots, the disposable worktree root, or the evidence root itself.

   Cleanup and pruning must use canonical containment checks and reject symlink, junction, or reparse-point escape. Normal run completion preserves the evidence directory. Expired-directory pruning removes only marker-verified owned descendants and surfaces failures.

4. Finalize artifacts after process output closes.

   For every declared retained file, validate the relative path, resolve it beneath the run evidence directory, require a regular non-symlink file, enforce per-file and total limits, stream SHA-256, record size and media type, and calculate retention expiry. Never trust artifact metadata supplied by a child process. Child processes may produce only files at trusted manifest-declared destinations.

   Existing stdout/stderr logs should become artifact records or explicitly declared log references with hashes. API output must contain safe relative POSIX-style paths only.

5. Parse bounded results.

   Add small trusted parsers for declared result kinds, starting with pytest counts and coverage JSON if the manifest actually produces them. Parsing failure must be represented truthfully as unavailable or parser-failed metadata without turning a successful validation command into fabricated structured success. Security commands should report bounded normalized status and tool identity rather than full scanner output.

6. Build and fingerprint the compact evidence document.

   After source-worktree cleanup and local artifact finalization, construct one strict evidence document from the approved work order, run identity, trusted manifest, worker registration/environment, step results, artifact records, cleanup status, and timestamps. Compute the SHA-256 fingerprint over canonical JSON with the fingerprint field omitted. Insert the fingerprint and validate the final document again before completion.

   Keep the existing bounded `result_summary` for concise human-readable status, but make `evidence_metadata` the authoritative compact structured document and `artifact_metadata` the authoritative strict artifact list.

7. Expose evidence through the API.

   Add `GET /api/execution/runs/{run_id}/evidence` under the existing admin-token execution router. Retrieve the run and associated work-order identity, validate persisted evidence and artifact JSON, and return the strict compact response. Return 404 for missing runs and an explicit server error for invalid persisted evidence; do not silently coerce malformed records.

8. Add tests and documentation.

   Add unit tests for every boundary and server-backed tests for completion and retrieval. Execute the complete workflow twice against temporary local repositories. Prove exact SHA, manifest digest, stable canonical fingerprint inputs, artifact hashes, retained local logs, source cleanup, and canonical-checkout integrity. Document configuration, disk policy, retention, privacy, and operator recovery.

## Concrete Steps

1. Verify local state before editing:

   ```text
   git fetch origin --prune
   git switch feat/exact-sha-validation-evidence
   git status --short --branch
   git rev-parse HEAD
   git rev-parse origin/feat/exact-sha-validation-evidence
   git rev-parse origin/main
   git merge-base HEAD origin/main
   ```

   Expected starting values:

   ```text
   HEAD: f549ab7bb2efc274dc2d79e12502d5653ddc8886 plus the initial ExecPlan commit
   branch: feat/exact-sha-validation-evidence
   origin/main ancestor: f549ab7bb2efc274dc2d79e12502d5653ddc8886
   working tree: clean
   ```

2. Read in full before implementation:

   ```text
   .agent/PLANS.md
   .agent/execplans/008_exact_sha_validation_evidence.md
   server/execution/registry.py
   server/execution/schemas.py
   server/execution/repository.py
   server/execution/service.py
   server/api/routers/execution.py
   server/models.py
   client/python/execution_worker/config.py
   client/python/execution_worker/models.py
   client/python/execution_worker/runner.py
   client/python/execution_worker/worker.py
   client/python/execution_worker/worktree.py
   docs/operations/local-worker.md
   ```

3. Implement in small reviewable commits, keeping this ExecPlan current after each meaningful discovery or decision.

4. Run focused tests first, using a repository-owned writable pytest temp directory when the environment default is restricted.

5. Run the complete repository validation documented in issue #114 and `.github/workflows/ci.yml`, including strict browser UI and the exact current coverage command.

6. Push only `feat/exact-sha-validation-evidence`. Do not force-push, rebase, merge `main`, create another branch, or open another PR.

## Validation and Acceptance

Acceptance requires all of the following:

- `validate-switchboard@1` is immutable, read-only, digest-bound, and metadata-only over the API.
- The worker rejects any manifest, work-order, capability, path, or executable mismatch before process launch.
- The tested repository and exact 40-character SHA in evidence match the approved work order and verified worktree `HEAD`.
- Full logs and artifacts exist only under the marked run evidence directory, never in the canonical checkout or API response.
- Every artifact path is relative, contained, regular, bounded, and SHA-256 verified.
- Retention expiry is deterministic and expired deletion is marker-verified and contained.
- Evidence JSON is strict, bounded, versioned, and contains no full logs, absolute paths, tokens, or arbitrary environment values.
- The fingerprint is deterministic for the documented canonical inputs and changes when an identity-defining input changes.
- Nonzero exits, timeouts, cancellation, ownership loss, parser failure, artifact failure, local-record failure, and cleanup failure remain truthful.
- The disposable source worktree is removed and the canonical checkout remains byte-for-byte unchanged.
- Two server-backed end-to-end validations complete against temporary repositories and return retrievable compact evidence.
- Focused tests, full pytest, lint, formatting, Mypy, coverage gates, security checks, Gitleaks, links, strict browser UI, and `git diff --check` pass.
- The PR remains draft and unmerged until connector review confirms the exact head and hosted matrix.

## Idempotence and Recovery

- Trusted manifest seeding must remain idempotent by name, version, and digest. A changed executable definition requires a new manifest version; never mutate an existing persisted identity silently.
- Evidence-directory creation must fail if the run directory or ownership marker already exists unexpectedly. Do not reuse or overwrite ambiguous evidence.
- Artifact hashing and evidence construction may be retried before completion only when all source files remain closed and unchanged.
- Completion writes remain non-retried because an ambiguous terminal write can duplicate or contradict ownership state.
- Expired-directory pruning is safe to repeat because only marker-verified expired descendants are eligible.
- If evidence finalization fails, report a truthful failed terminal result when ownership remains, preserve diagnostic local files when safe, and do not fabricate a fingerprint.
- If ownership is lost, stop work and do not send stale completion, matching the #113 worker contract.

## Artifacts and Notes

Initial connector planning evidence:

- PR #119 merged to `main` as `f549ab7bb2efc274dc2d79e12502d5653ddc8886` and closed issue #113.
- Issue #114 now records the exact base SHA, canonical branch, `validate-switchboard@1`, local evidence boundary, compact endpoint, retention, fingerprint, tests, and forbidden scope.
- Existing database JSON columns and completion transport are sufficient for the first strict compact contract; no migration or artifact upload endpoint is planned unless implementation proves otherwise.

Do not commit real tokens, absolute operator paths, full environment dumps, generated evidence, test databases, virtual environments, or worker-owned runtime directories.

## Interfaces and Dependencies

Expected new or strengthened interfaces include:

- strict server models such as `ArtifactRecord`, `StepEvidence`, `EnvironmentEvidence`, `ExecutionEvidence`, and `ExecutionEvidenceOut` under `server/execution/schemas.py` or a focused imported schema module;
- a canonical JSON and fingerprint helper shared by worker construction and server validation without importing executable worker code into request handlers;
- `GET /api/execution/runs/{run_id}/evidence` returning the strict compact response;
- worker configuration fields for evidence root, retention days, artifact count, per-artifact bytes, and total evidence bytes;
- a focused local evidence store responsible for ownership markers, contained paths, hashing, retention, and pruning;
- trusted step parser declarations in safe metadata, with parser implementations selected only by reviewed manifest definitions;
- `validate-switchboard@1` in the trusted registry with no caller-controlled argv;
- no new runtime dependency unless a documented cross-platform containment or parsing requirement cannot be satisfied safely with the standard library and existing packages.
