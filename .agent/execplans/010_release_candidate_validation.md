# Validate the public-preview release candidate

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This repository implements the Switchboard service. This plan must be maintained in accordance with `.agent/PLANS.md`.

Primary issue: #104. Parent release tracker: #95.

## Purpose / Big Picture

Produce truthful Linux, clean-environment, Docker, security, coverage, browser, and public-release evidence for one immutable Switchboard commit. The selected candidate is the `main` commit created by squash-merging documentation PR #126:

```text
b79aba1aaf72ffd20f0221bdf0fd77552541073f
```

The candidate remains classified as `PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY`. Successful validation may support a later owner release decision, but this plan does not authorize a tag, release, deployment, production-readiness claim, or internet-facing service.

## Progress

- [x] PR #126 squash-merged after explicit owner authorization.
- [x] Immutable candidate SHA selected: `b79aba1aaf72ffd20f0221bdf0fd77552541073f`.
- [x] Release-evidence branch created from exactly that SHA.
- [x] Living ExecPlan created.
- [x] Verify the isolated checkout and candidate identity.
- [x] Capture Linux, kernel, Python, pip, Git, Docker, browser, and validation-tool versions.
- [x] Run the Linux symlink-containment regression without a skip.
- [x] Run every executable clean-environment validation gate.
- [x] Attempt the server Docker build and record the precise unavailable-client blocker.
- [x] Update `PUBLIC_RELEASE_AUDIT.md` with exact executed evidence.
- [x] Complete public-repository hygiene and generated-artifact cleanup.
- [x] Push the evidence update to the existing release branch.
- [x] Record hosted workflow IDs and connector review.

## Surprises & Discoveries

- Observation: Ubuntu did not provide Python 3.11 in the base environment.
  Evidence: a standalone Python 3.11.14 runtime and isolated task-only virtual environment were provisioned outside the repository; dependency installation and `pip check` passed.

- Observation: Playwright's privileged Linux dependency installer required unavailable administrative credentials.
  Evidence: Chromium 140.0.7339.16 and the required runtime libraries were provisioned in an isolated user environment instead. The complete suite and the strict two-test browser suite then passed.

- Observation: the WSL2 environment did not expose a Docker command.
  Evidence: the required `docker build -f server/Dockerfile .` attempt failed before build startup with `docker: command not found`. No system-wide daemon was installed or reconfigured.

- Observation: the all-files pre-commit command can mutate files by design.
  Evidence: it was executed in a disposable detached validation copy at the exact candidate SHA. Every hook passed and that copy remained unchanged.

## Decision Log

- Decision: validate exactly `b79aba1aaf72ffd20f0221bdf0fd77552541073f`.
  Rationale: this is the immutable `main` commit produced by the explicitly authorized PR #126 documentation merge. It contains the merged Phase 1 execution/evidence foundation and the reviewed public-preview documentation boundary.
  Date/Author: 2026-07-26 / owner and connector coordination

- Decision: exclude PR #125 and issues #121/#122 from this release candidate.
  Rationale: Phase 2 is valuable but is not a formal-release prerequisite. Adding it now would move the candidate after validation began and broaden the security and persistence surface under review.
  Date/Author: 2026-07-26 / owner and connector coordination

- Decision: use one narrow branch, `release/public-preview-candidate-validation`, for the living plan and final audit evidence.
  Rationale: release evidence must not modify `main`, PR #125, or Phase 2 branches. Any reproduced gate failure must be corrected minimally on this branch and reviewed separately.
  Date/Author: 2026-07-26 / connector coordination

- Decision: retain the developer-preview classification unless a later owner decision explicitly changes it.
  Rationale: validation alone does not establish support for untrusted multi-tenant or direct internet-facing deployment, nor does it satisfy owner-controlled repository settings and alert review.
  Date/Author: 2026-07-26 / connector coordination

- Decision: retain `b79aba1aaf72ffd20f0221bdf0fd77552541073f` as the immutable tested candidate despite the Docker environment blocker.
  Rationale: all executable source, security, browser, coverage, and Linux symlink gates passed without a source correction. Installing or reconfiguring a system-wide Docker daemon was outside the authorized environment preparation.
  Date/Author: 2026-07-27 / validation executor

## Outcomes & Retrospective

Candidate `b79aba1aaf72ffd20f0221bdf0fd77552541073f` was validated on Ubuntu 24.04.3 LTS under WSL2, kernel `6.18.33.2-microsoft-standard-WSL2`, architecture `x86_64`. The mandatory symlink-containment regression executed and passed with zero skips. The complete Python suite passed with 386 passes and 2 intentional skips; the strict browser suite passed 2 tests with zero skips. Aggregate coverage was 91%, and every configured module threshold passed.

Dependency integrity, pre-commit, TODO policy, Ruff, Black, Mypy, Bandit, pip-audit, full-history Gitleaks, and Lychee all passed. The only unexecuted build was Docker: the WSL2 environment had no Docker command, and the authorized process prohibited installing or reconfiguring a system-wide daemon. The candidate was not changed to work around that limitation.

Generated caches, reports, coverage data, and the temporary test database were removed. Final candidate verification showed the exact detached SHA, no diff-check errors, and a clean worktree. The public classification remains `PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY`; validation does not authorize a tag, release, production deployment, untrusted multi-tenant use, or direct internet exposure. Formal release remains blocked on Docker-capable validation and the owner-controlled repository settings and alert review tracked in issue #95.

## Context and Orientation

- `PUBLIC_RELEASE_AUDIT.md` is the durable public release-evidence record.
- `server/tests/test_live_files.py` contains the Linux symlink-containment regression.
- `.github/workflows/ci.yml` defines the protected hosted matrix and current command expectations.
- `scripts/dev.py` implements TODO and module-coverage gates.
- `server/requirements-dev.txt` is the audited Python validation dependency set.
- `server/Dockerfile` is the required Docker build target.
- `lychee.toml` defines documentation link validation.
- Issue #95 tracks formal release and owner-controlled repository gates.
- Issue #104 tracks this exact Linux, Docker, and clean-environment pass.
- PR #125 remains separate, ready, and unmerged; it must not be merged, rebased, or absorbed into this branch during this work.

## Plan of Work

1. Create or use a disposable Linux-capable clone or worktree at exactly the candidate SHA. Verify no local branch or uncommitted state can change the candidate under test.
2. Create a clean Python 3.11 environment outside the repository and install the candidate's exact development requirements plus pre-commit.
3. Record the operating-system, kernel, architecture, Git, Python, pip, Docker, browser, and validation-tool versions.
4. Run the targeted symlink-containment test first. It must execute and pass without skipping.
5. Run dependency integrity, pinned pre-commit, TODO policy, Ruff, Black, Mypy, full pytest, strict browser, configured coverage, Bandit, pip-audit, full-history Gitleaks, and Lychee.
6. Build the Docker image from `server/Dockerfile` and record the resulting image identity, or record a precise external blocker without weakening the gate.
7. Review all generated output and delete reports, caches, databases, images exported to files, logs, and temporary artifacts from the worktree.
8. Update only this ExecPlan and `PUBLIC_RELEASE_AUDIT.md`, unless a reproduced release-gate defect requires a minimum correction. Any correction must include focused regression coverage and the entire matrix must be rerun.
9. Commit intentionally, push only the existing release branch, keep its PR draft, and record hosted workflow results.

## Concrete Steps

Start from a clean Linux-capable environment:

```bash
git fetch origin --prune
git rev-parse HEAD
git rev-parse origin/main
git status --short --branch
git worktree list --porcelain
```

Require the tested checkout and selected candidate to resolve to:

```text
b79aba1aaf72ffd20f0221bdf0fd77552541073f
```

Capture environment versions:

```bash
uname -a
cat /etc/os-release
uname -m
git --version
python3.11 --version
python3.11 -m pip --version
docker version
```

Create and activate a clean Python 3.11 environment outside the repository, then run:

```bash
python -m pip install --upgrade pip
python -m pip install -r server/requirements-dev.txt
python -m pip install pre-commit
python -m pip check

python -m pre_commit run --all-files --show-diff-on-failure
python scripts/dev.py check-todos --root .
python -m ruff check server client scripts tests web switchboard_cli.py switchboard_client.py
python -m black --check server client scripts tests web switchboard_cli.py switchboard_client.py
python -m mypy --config-file mypy.ini server client scripts

mkdir -p reports
python -m pytest server/tests/test_live_files.py::test_live_file_symlink_escape_blocked_for_read_and_write -q -rA
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
  "docs/**/*.md" \
  --exclude-path docs/history \
  --exclude-path archive

docker build -f server/Dockerfile .
git diff --check
git status --short --branch --untracked-files=all
```

Use the candidate's exact installed command forms if entry points differ. Do not skip or weaken a gate.

## Validation and Acceptance

Acceptance requires all of the following:

- the tested source commit is exactly `b79aba1aaf72ffd20f0221bdf0fd77552541073f`;
- the Linux symlink regression executes and passes without a skip;
- clean Python 3.11 dependency installation and `pip check` pass;
- pre-commit, TODO, Ruff, Black, and Mypy pass without mutation;
- full pytest and strict browser pass, with browser tests not skipped;
- aggregate coverage and all configured module thresholds pass;
- Bandit, pip-audit, Gitleaks, and Lychee pass;
- Docker builds successfully or a precise external blocker is documented;
- the candidate checkout remains unchanged;
- `PUBLIC_RELEASE_AUDIT.md` truthfully records exact commands, versions, counts, coverage, security, Docker, limitations, and remaining owner-only gates;
- no release, tag, deployment, or production-readiness claim is created automatically.

## Idempotence and Recovery

- Recreate the disposable checkout rather than cleaning an uncertain one.
- Never move the selected candidate during this evidence pass.
- Generated reports and caches may be deleted and regenerated safely.
- If a gate fails, preserve the failure output outside the repository, record the precise command and cause, and make only a minimum justified correction on the release branch.
- After any correction, rerun the targeted regression and complete matrix.
- Do not rebase, force-push, merge PR #125, or modify Phase 2 branches.

## Artifacts and Notes

Record during execution:

- exact candidate SHA;
- OS, kernel, architecture, Git, Python, pip, Docker, browser, pre-commit, Ruff, Black, Mypy, pytest, Bandit, pip-audit, Gitleaks, and Lychee versions;
- targeted Linux symlink result and proof that it did not skip;
- full pytest and strict browser counts;
- aggregate coverage and every module threshold;
- security, dependency, secret, and link results;
- Docker image ID or precise blocker;
- final `git diff --check` and clean-tree state;
- exact remaining owner-controlled repository settings and alert review.

Recorded evidence:

- environment: Ubuntu 24.04.3 LTS; kernel `6.18.33.2-microsoft-standard-WSL2`; `x86_64`;
- tools: Git 2.43.0; Python 3.11.14; pip 26.1.2; Chromium 140.0.7339.16; Playwright 1.55.0; pre-commit 4.6.1; Ruff 0.14.2; Black 26.5.1; Mypy 1.18.2; pytest 9.1.1; Bandit 1.8.6; pip-audit 2.7.3; Gitleaks 8.30.1; Lychee 0.24.2;
- Linux symlink regression: 1 passed, zero skipped;
- full pytest: 386 passed, 2 skipped, 5 warnings;
- strict browser: 2 passed, zero skipped;
- aggregate coverage: 91%;
- configured module thresholds: all 16 satisfied, with exact percentages recorded in `PUBLIC_RELEASE_AUDIT.md`;
- Lychee: 176 links inspected, 0 errors and 0 timeouts;
- Gitleaks: 162 commits scanned, no leaks;
- Docker: unavailable in WSL2 (`docker: command not found`), so no image ID exists;
- final candidate state: detached at the selected SHA, `git diff --check` clean, no tracked or untracked files.
- evidence commit: `a87c3029c074b4c703e72c80a33b89e18212a8d3`;
- hosted evidence: Commitlint `30252655080` — success; CI `30252655221` — success;
- connector planning review `4782954620` established the immutable-candidate, public-hygiene, Docker-blocker, and draft-release boundaries reflected in this evidence.

## Interfaces and Dependencies

No new runtime interface is planned. The expected final diff is limited to:

- `.agent/execplans/010_release_candidate_validation.md`;
- `PUBLIC_RELEASE_AUDIT.md`.

A reproduced release-gate defect may justify a minimum additional correction only when accompanied by focused tests and complete revalidation.
