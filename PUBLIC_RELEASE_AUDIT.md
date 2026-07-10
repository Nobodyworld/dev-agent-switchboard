# Public Release Audit — Final Candidate

**Classification:** `KEEP PRIVATE - NEAR READY`
**Current main after Actions and security-control merges:** `59c6c19d27ab6d60684ec7fda13592db63fbf591`
**Clean-clone implementation candidate:** `a143e1a6a4187f648fe9c58c340215af9d11c51d`
**Audit date:** 2026-07-10
**Repository:** `Nobodyworld/dev-agent-switchboard`

## Scope

This audit separates executed evidence from remaining publication mechanics.

The clean-clone implementation results below apply to candidate `a143e1a6a4187f648fe9c58c340215af9d11c51d`. Subsequent release-documentation commits, the Actions repair merged in PR #94, and the Dependabot/security-control work merged in PR #96 did not change application runtime behavior, but final publication still requires validation against the final merged `main` SHA.

Historical results from earlier candidates are not release authority.

## Governance and Showcase Artifacts

- `LICENSE` contains canonical Apache License 2.0 text.
- `NOTICE` contains project attribution.
- `SECURITY.md`, `CONTRIBUTING.md`, and support documentation describe a best-effort solo-maintainer posture.
- A real dashboard screenshot is stored at `docs/assets/switchboard-dashboard.png`.
- Architecture, API, configuration, integration, and workflow documentation are present.
- `.github/dependabot.yml` covers server and Python-client dependencies, Docker, and GitHub Actions.
- `docs/release/PRIVATE_REPOSITORY_SECURITY.md` records private-repository deferrals and publication controls.

**Status:** PASS for the current release line; rerun formatting and link checks after this final documentation merge.

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

PR #96 also passed Commitlint run `29122579502` and CI run `29122579510` before merge. Its CI included the same eight successful jobs.

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

### 1. Linux symlink-containment execution

Run the targeted regression on Linux, WSL with working symlink support, or a Linux container/runner:

```bash
pytest server/tests/test_live_files.py::test_live_file_symlink_escape_blocked_for_read_and_write -q -rA
```

Required result:

- the test executes rather than skips;
- read and write attempts through an escaping symlink are rejected;
- the result is recorded against the final release candidate.

### 2. Final-main validation

After this final documentation PR is merged:

1. record the final `main` SHA;
2. confirm hosted `CI` and `Commitlint` passed on this PR's merge candidate;
3. rerun pre-commit and `git diff --check` locally if a clean-clone sign-off is required;
4. rerun full-history Gitleaks against final `main` if the merge commit is not already covered by hosted validation;
5. validate the Docker build if Docker remains advertised as supported;
6. confirm no release-blocking PRs remain;
7. update this audit with final Linux, Docker, settings, and final-main evidence.

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

## Final Verdict

Switchboard's implementation, local quality gates, hosted CI, security controls, dependency automation, documentation, canonical license, and visual evidence are substantially ready for a public showcase.

Publication is not yet authorized because:

- Linux symlink-containment validation has not executed successfully;
- final-main clean-clone and Docker sign-off remain optional but recommended release evidence;
- repository protection and publication settings remain owner-controlled gates.

```text
KEEP PRIVATE - NEAR READY
```
