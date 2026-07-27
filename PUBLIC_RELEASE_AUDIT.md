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
| Docker      | Unavailable; no client or server version     |

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
| Docker build       | BLOCKED | Docker command unavailable before build startup           |

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

## Docker Blocker

The required build command was attempted against the detached candidate and failed before build startup because the WSL2 environment did not expose a Docker command:

```text
docker: command not found
```

No image was built, so no image ID exists. The validation scope expressly prohibited automatically installing or reconfiguring a system-wide Docker daemon. This is an environment limitation, not a reproduced source defect, and the candidate was not modified to work around it.

Formal release authorization remains blocked until the same immutable candidate is built successfully in a Docker-capable environment or an owner deliberately selects and validates a successor candidate.

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

Candidate `b79aba1aaf72ffd20f0221bdf0fd77552541073f` passed every executable Linux source, test, browser, coverage, dependency, security, secret, and link gate. The mandatory symlink regression passed without a skip. Docker validation remains blocked by the unavailable client, so formal release authorization remains blocked.

The repository remains suitable for public source publication and controlled developer evaluation under:

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

This validation does not authorize a tag, release, deployment, production-readiness claim, untrusted multi-tenant use, or direct internet-facing operation.
