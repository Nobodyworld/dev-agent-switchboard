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
- [ ] Define strict versioned artifact and compact evidence models.
- [ ] Add the trusted `validate-switchboard@1` manifest and immutable safe metadata.
- [ ] Add a worker-owned evidence-directory lifecycle separate from the disposable source worktree.
- [ ] Add artifact validation, hashing, redaction metadata, and retention expiry.
- [ ] Add deterministic evidence fingerprinting from canonical JSON.
- [ ] Extend worker step results with timestamps and declared parsed result kinds.
- [ ] Complete runs with strict evidence and artifact metadata.
- [ ] Add `GET /api/execution/runs/{run_id}/evidence`.
- [ ] Add marker-verified retention cleanup for expired evidence directories.
- [ ] Add focused security, schema, fingerprint, parser, retention, and API tests.
- [ ] Add two server-backed exact-SHA end-to-end executions against temporary repositories.
- [ ] Update operator and API documentation.
- [ ] Run the complete repository validation and protected hosted matrix.
- [ ] Record final evidence, limitations, and merge result here.

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

## Outcomes & Retrospective

Not complete. At completion, record:

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
