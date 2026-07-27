# Public Developer Preview Audit — Formal Release Still Blocked

**Classification:** `PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY`
**Validated candidate:** `b79aba1aaf72ffd20f0221bdf0fd77552541073f`
**Public visibility disposition:** `ALLOWED FOR SOURCE PUBLICATION`
**Formal release authorization:** `BLOCKED`
**Production deployment authorization:** `NOT AUTHORIZED`
**Audit updated:** 2026-07-27
**Repository:** `Nobodyworld/dev-agent-switchboard`

## Decision Boundaries

This audit separates public source visibility, developer-preview availability, formal release authorization, and production deployment safety. Public source visibility permits inspection and controlled local evaluation. It does not authorize a version tag, general-availability release, hosted public service, production deployment, untrusted multi-tenant use, or direct internet exposure.

The immutable source candidate validated here is:

```text
b79aba1aaf72ffd20f0221bdf0fd77552541073f
```

The release-evidence branch and draft PR #127 contain only the living validation plan and this audit. Their branch head is not the candidate under test. PR #125 and issues #121/#122 remain outside this candidate and were not merged, rebased, or incorporated during validation.

## Linux Validation Environment

Validation ran in a detached, clean Linux worktree using an isolated Python environment outside the repository.

| Component   | Version or disposition                       |
| ----------- | -------------------------------------------- |
| OS          | Ubuntu 24.04.3 LTS under WSL2                |
| Kernel      | `6.18.33.2-microsoft-standard-WSL2`          |
| Architecture | `x86_64`                                    |
| Git         | 2.43.0                                       |
| Python      | 3.11.14                                      |
| pip         | 26.1.2                                       |
| Chromium    | 140.0.7339.16, Playwright build 1187         |
| Playwright  | 1.55.0                                       |
| pre-commit  | 4.6.1                                        |
| Ruff        | 0.14.2                                       |
| Black       | 26.5.1                                       |
| Mypy        | 1.18.2                                       |
| pytest      | 9.1.1                                        |
| Bandit      | 1.8.6                                        |
| pip-audit   | 2.7.3                                        |
| Gitleaks    | 8.30.1                                       |
| Lychee      | 0.24.2                                       |
| Docker (initial WSL2) | Unavailable; no local client or server     |

The base environment did not provide Python 3.11, so a standalone Python 3.11.14 runtime was used. Playwright's privileged dependency installer required unavailable administrative credentials; Chromium and its required runtime libraries were instead provisioned in an isolated user environment. No repository dependency or source change was made for either condition.

## Mandatory Linux Symlink Gate

The exact Linux symlink-containment regression executed first:

```text
server/tests/test_live_files.py::test_live_file_symlink_escape_blocked_for_read_and_write
```

Result: **PASS — 1 passed, 0 skipped**.

The test proved that escaping symlink reads and writes are rejected. It was not weakened, skipped, xfailed, or bypassed.

## Complete Validation Evidence

| Gate               | Result | Evidence                                                   |
| ------------------ | ------ | ---------------------------------------------------------- |
| Dependency install | PASS   | Exact development requirements installed in isolation      |
| pip integrity      | PASS   | No broken requirements                                     |
| pre-commit         | PASS   | All hooks passed; exact-SHA validation copy unchanged      |
| TODO policy        | PASS   | Repository TODO policy satisfied                           |
| Ruff               | PASS   | All checks passed                                          |
| Black              | PASS   | No formatting changes required                             |
| Mypy               | PASS   | No issues in 162 configured source files                   |
| Full pytest        | PASS   | 386 passed, 2 skipped, 5 warnings                          |
| Strict browser     | PASS   | 2 passed, 0 skipped                                        |
| Aggregate coverage | PASS   | 91%; 1,449 of 1,586 statements covered                     |
| Bandit             | PASS   | No findings                                                |
| pip-audit          | PASS   | No known vulnerabilities                                   |
| Gitleaks           | PASS   | 162 commits scanned; no leaks                              |
| Lychee             | PASS   | 176 links inspected; 0 errors and 0 timeouts               |
| Docker build       | PASS   | Exact candidate built on GitHub-hosted Ubuntu 24.04        |

The two full-suite skips were the repository's intentional non-strict browser skips. The separate strict browser invocation executed both browser tests and proved zero skips.

The all-files pre-commit command was run in a disposable detached copy at the identical candidate SHA to prevent mutating hooks from touching the formal candidate. Its source bytes matched the candidate, every hook passed, and it remained unchanged.

## Coverage Thresholds

Aggregate coverage was 91%. Every configured module threshold passed:

| Module                                                | Required | Actual  |
| ----------------------------------------------------- | -------: | ------: |
| `server/extensions/contracts.py`                      |      85% |  95.40% |
| `server/extensions/interfaces.py`                     |      85% |  94.17% |
| `server/extensions/loader.py`                         |      85% | 100.00% |
| `server/extensions/runtime.py`                        |      85% | 100.00% |
| `server/extensions/builtin/task_metrics.py`           |      85% |  92.59% |
| `server/extensions/builtin/plan_metrics.py`           |      85% |  95.00% |
| `server/extensions/builtin/plan_latency.py`           |      80% |  87.76% |
| `server/extensions/builtin/plan_snapshot.py`          |      80% | 100.00% |
| `server/extensions/builtin/activity_feed.py`          |      85% | 100.00% |
| `server/extensions/observability.py`                  |      80% |  97.73% |
| `server/observability/diagnostics.py`                 |      80% |  90.16% |
| `server/observability/health.py`                      |      85% |  95.78% |
| `server/observability/activity.py`                    |      80% |  94.83% |
| `server/observability/overview.py`                    |      85% | 100.00% |
| `server/application/task_service.py`                 |      75% |  79.23% |
| `server/application/configuration_service.py`        |      85% |  91.30% |

## Exact-Candidate Hosted Docker Evidence

The initial WSL2 environment did not expose a Docker command. That was an environment limitation, not the final candidate disposition. No system-wide daemon was installed or reconfigured, and the candidate was not modified to work around the local limitation.

The connector subsequently used a temporary workflow to build exactly:

```text
b79aba1aaf72ffd20f0221bdf0fd77552541073f
```

The workflow used read-only `contents` permission and full-length SHA-pinned actions. It checked out the immutable candidate rather than the PR merge ref, verified candidate identity and a clean source tree before the build, ran:

```text
docker build --pull=false --tag switchboard-release-candidate:b79aba1aaf72 -f server/Dockerfile .
```

and verified the candidate remained unchanged afterward. The bounded hosted evidence is:

| Evidence            | Value                                                                      |
| ------------------- | -------------------------------------------------------------------------- |
| Workflow            | `30300834437`                                                              |
| Job                 | `90093063000`                                                              |
| Hosted environment  | GitHub-hosted Ubuntu 24.04                                                  |
| Docker client       | 28.0.4                                                                     |
| Docker server       | 28.0.4                                                                     |
| Image ID            | `sha256:b7cf3898a97d16989c8684c1a8a26d7d637cfc84262dcb7d6cdc1aa9efba7bc7` |
| Artifact            | `8666477133`                                                               |
| Artifact digest     | `sha256:c2c497c00430beeed52a8688abc37b06fdf65d6fd09371c47bf0295a749fcfc2` |

The workflow uploaded only the bounded candidate SHA, Docker versions, and image ID. It was deleted after evidence retrieval and is absent from the final PR diff.

Docker validation now passes. Formal release authorization remains separate from technical validation and still requires review of this evidence PR and the owner-controlled repository and security settings tracked in issue #95.

## Candidate Immutability and Public Hygiene

After each major stage, the detached worktree still resolved to `b79aba1aaf72ffd20f0221bdf0fd77552541073f`. Generated caches, coverage data, reports, temporary databases, browser artifacts, and link-checker state were removed. Final verification showed:

- detached candidate HEAD exactly matched the selected SHA;
- `git diff --check` passed;
- no tracked or untracked candidate files remained;
- no source correction was made;
- no credentials, machine identity, private URLs, environment dumps, logs, generated databases, or generated reports were added to the evidence branch.

## Governance and Remaining Owner Actions

The repository continues to provide its Apache License 2.0 license and notice, security and contribution policies, architecture and operator documentation, showcase assets, Dependabot configuration, and pinned read-only hosted workflow controls.

Issue #95 remains the system of record for owner-controlled release work. An owner comment reports that the `main` protection rule is configured for pull requests, conversation resolution, force-push blocking, branch-deletion blocking, and public checks. The formal checklist still requires owner verification of those controls and the intended required checks and merge/history policy.

The following owner-controlled items remain:

- enable or verify CodeQL Default Setup;
- review CodeQL, Dependabot, and secret-scanning alerts;
- enable or verify Dependabot security updates;
- verify Secret Protection and Push Protection when available;
- verify repository description, topics, license detection, and social preview;
- make any later formal tag, release, or deployment decision explicitly.

Hosted Commitlint and CI results for the final evidence commit will be recorded in the living ExecPlan after the branch is pushed.

## Final Verdict

Candidate `b79aba1aaf72ffd20f0221bdf0fd77552541073f` passed every technical Linux, Docker, test, browser, coverage, quality, dependency, security, secret, and link gate. The mandatory symlink regression passed without a skip, and the exact-candidate hosted Docker build passed without changing the source.

Formal release authorization is not automatic. It remains a separate owner decision requiring review of this evidence PR and the owner-controlled repository and security settings tracked in issue #95.

The repository remains suitable for public source publication and controlled developer evaluation under:

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

This validation does not authorize a tag, release, deployment, production-readiness claim, untrusted multi-tenant use, or direct internet-facing operation.
