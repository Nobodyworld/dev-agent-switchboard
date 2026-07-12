# Public Release Audit — Final Candidate

**Classification:** `KEEP PRIVATE - NEAR READY`
**Release-line baseline before this audit correction:** `12c579964dd8c87e05e31aad8a76426fda0d407d`
**Validated base before the final documentation merge:** `59c6c19d27ab6d60684ec7fda13592db63fbf591`
**Final documentation merge-candidate head:** `e3a4605f7d61978573b94435527546c194561187`
**Clean-clone implementation candidate:** `a143e1a6a4187f648fe9c58c340215af9d11c51d`
**Audit updated:** 2026-07-11
**Repository:** `Nobodyworld/dev-agent-switchboard`

## Scope

This audit separates executed evidence from remaining publication mechanics.

The clean-clone implementation results below apply to candidate `a143e1a6a4187f648fe9c58c340215af9d11c51d`. Subsequent release-documentation commits, the Actions repair merged in PR #94, the Dependabot/security-control work merged in PR #96, and the final public-documentation work merged in PR #97 did not change application runtime behavior.

The release-line baseline `12c579964dd8c87e05e31aad8a76426fda0d407d` is the last merged commit before this audit-only correction. This document does not attempt to identify its own future merge commit. Final publication authority must reference the immutable release commit or tag produced after issue #104 and the owner-controlled repository settings review are complete.

Historical results from earlier candidates are not release authority.

## Governance and Showcase Artifacts

- `LICENSE` contains canonical Apache License 2.0 text.
- `NOTICE` contains project attribution.
- `SECURITY.md`, `CONTRIBUTING.md`, and support documentation describe a best-effort solo-maintainer posture.
- A real dashboard screenshot is stored at `docs/assets/switchboard-dashboard.png`.
- Architecture, API, configuration, integration, and workflow documentation are present.
- `.github/dependabot.yml` covers server and Python-client dependencies, Docker, and GitHub Actions.
- `docs/release/PRIVATE_REPOSITORY_SECURITY.md` records private-repository deferrals and publication controls.

**Status:** PASS on PR #97. This audit-only correction must pass the same formatting and link-validation gates before merge.

## Clean-Clone Release Gates

Validation was executed from a fresh local checkout using Python 3.11.14.

| Gate                                                          | Result | Evidence                                 |
| ------------------------------------------------------------- | ------ | ---------------------------------------- |
| `python -m pip check`                                         | PASS   | No broken requirements found             |
| `python -m pre_commit run --all-files --show-diff-on-failure` | PASS   | All hooks passed; no mutations           |
| Ruff                                                          | PASS   | All checks passed                        |
| Black                                                         | PASS   | No formatting changes required           |
| Mypy                                                          | PASS   | No issues in 119 configured source files |
| `pytest -q`                                                   | PASS   | 229 passed, 2 skipped, 5 warnings        |
| Strict Playwright                                             | PASS   | 2 passed                                 |
| Aggregate coverage                                            | PASS   | 87%; 229 passed, 2 skipped               |
| Module coverage gate                                          | PASS   | Thresholds satisfied                     |
| Bandit                                                        | PASS   | No findings                              |
| `pip-audit`                                                   | PASS   | No known vulnerabilities                 |
| Gitleaks                                                      | PASS   | No leaks found in the validated history  |
| Lychee link validation                                        | PASS   | 162 links OK, 0 errors                   |

Representative commands:

```bash
python -m pip check
python -m pre_commit run --all-files --show-diff-on-failure
ruff check server client scripts tests web switchboard_cli.py switchboard_client.py
black --check server client scripts tests web switchboard_cli.py switchboard_client.py
mypy --config-file mypy.ini server client scripts
pytest -q
SWITCHBOARD_STRICT_PLAYWRIGHT=1 pytest web/tests/test_ui.py -rA
pytest --cov=server --cov=client --cov=scripts --cov-report=term-missing --cov-report=json:reports/coverage.json -q
python scripts/dev.py coverage-gate --json reports/coverage.json
python -m bandit -q -r server -x server/tests
python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt
gitleaks detect --verbose --report-format json --report-path reports/gitleaks.json
```

## Hosted GitHub Actions Evidence

The repository-wide `startup_failure` was resolved in PR #94 by removing blocked third-party action references, pinning retained GitHub-owned actions to full commit SHAs, narrowing permissions, and correcting workflow/tool configuration.

Successful proof runs on PR #94 head `8b2dab001c1ca9a1d38f8faf48e4e4216932ba61`:

| Workflow/job     | Run/result                                |
| ---------------- | ----------------------------------------- |
| Commitlint       | Run `29121887721` — PASS                  |
| CI workflow      | Run `29121887745` — PASS                  |
| lint             | PASS                                      |
| typecheck        | PASS                                      |
| test             | PASS                                      |
| security         | PASS                                      |
| Secrets audit    | PASS                                      |
| Link check       | PASS                                      |
| Coverage         | PASS                                      |
| Browser UI tests | PASS; strict tests executed without skips |

PR #96 passed Commitlint run `29122579502` and CI run `29122579510` before merge. Its CI included the same eight successful jobs.

PR #97 passed Commitlint run `29122756381` and CI run `29122756348` before merge. Its CI included lint, typecheck, tests, security, full-history Gitleaks, link validation, coverage, and strict browser UI execution without skips.

The repaired workflows use read-only permissions and disable checkout credential persistence. Full history is fetched only where commit ranges or Gitleaks require it.

## Security-Control Evidence

Targeted validation covered:

1. health endpoint behavior;
2. readiness dependency reporting;
3. two-agent dependency unlocking and WebSocket updates;
4. admin-token protection for live-file mutations;
5. upload-size enforcement;
6. rate limiting;
7. symlink traversal prevention.

Executed result:

```text
6 passed, 1 skipped
```

The symlink test skipped because the Windows validation environment could not create the required symlink without additional privileges. The implementation uses resolved paths and root containment, but code review is not a substitute for executing the regression test on Linux.

## Remaining Publication Blockers

### 1. Linux symlink-containment and final local validation

Issue #104 is the system of record for the required Linux-capable execution, final clean-clone validation, and Docker build evidence.

The critical targeted command is:

```bash
pytest server/tests/test_live_files.py::test_live_file_symlink_escape_blocked_for_read_and_write -q -rA
```

Required result:

- the test executes rather than skips;
- read and write attempts through an escaping symlink are rejected;
- the complete required command set in issue #104 is recorded against the tested SHA;
- Docker either builds successfully or a precise blocker is recorded.

### 2. Final release identity and audit evidence

After issue #104 is complete:

1. identify the immutable release commit or tag;
2. record the Linux symlink result and Docker disposition;
3. record any final clean-clone evidence;
4. confirm no release-blocking pull requests remain;
5. update this audit with the final release authorization or remaining blocker.

### 3. Repository protection and publication settings

Before changing visibility:

- require pull requests before merging to `main`;
- require conversation resolution;
- block force pushes and branch deletion;
- confirm the desired merge/history policy;
- add required checks using the proven final check names;
- confirm Dependabot alerts and security updates;
- verify repository description, topics, license detection, and social preview.

After publication, enable or verify CodeQL Default Setup, Secret Protection, and Push Protection when available. Review initial alerts before treating those services as clean.

Parent issue #95 remains the publication checklist and issue #104 contains the executable local handoff.

## Final Verdict

Switchboard's implementation, local quality gates, hosted CI, security controls, dependency automation, documentation, canonical license, and visual evidence are substantially ready for a public showcase.

Publication is not yet authorized because:

- Linux symlink-containment validation has not executed successfully;
- final clean-clone and Docker evidence must be completed or explicitly dispositioned under issue #104;
- repository protection and publication settings remain owner-controlled gates.

```text
KEEP PRIVATE - NEAR READY
```
