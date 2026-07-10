# Public Release Audit — Final Candidate

**Classification:** `KEEP PRIVATE - NEAR READY`  
**Validated implementation candidate:** `a143e1a6a4187f648fe9c58c340215af9d11c51d`  
**Audit record updated through:** `189ca80b2d02f1c229133427de85d46369627a4c`  
**Audit date:** 2026-07-10  
**Repository:** `Nobodyworld/dev-agent-switchboard`

## Scope

This audit separates executed validation from remaining publication mechanics.

The implementation and test evidence below apply to candidate `a143e1a6a4187f648fe9c58c340215af9d11c51d`. Subsequent commits through `189ca80b2d02f1c229133427de85d46369627a4c` update release documentation and evidence metadata rather than application runtime behavior.

Any later documentation, workflow, or dependency commits still require the relevant final-HEAD checks before publication. Historical results from older implementation candidates are not used as release authority.

## Governance and Publication Artifacts

- `LICENSE` contains canonical Apache License 2.0 text.
- `NOTICE` contains project attribution.
- `SECURITY.md`, `CONTRIBUTING.md`, and support documentation describe a solo-maintainer, best-effort support model.
- A real dashboard screenshot is stored at `docs/assets/switchboard-dashboard.png`.
- Architecture, API, configuration, integration, and workflow documentation are present.

**Status:** PASS for the validated candidate; recheck documentation links and formatting on final HEAD.

## Clean-Clone Release Gates

Validation was executed from a fresh local checkout using Python 3.11.14.

| Gate | Result | Evidence |
|---|---|---|
| `python -m pip check` | PASS | No broken requirements found |
| `python -m pre_commit run --all-files --show-diff-on-failure` | PASS | All hooks passed; no mutations |
| Ruff | PASS | All checks passed |
| Black | PASS | No formatting changes required |
| Mypy | PASS | No issues in 119 configured source files |
| `pytest -q` | PASS | 229 passed, 2 skipped, 5 warnings |
| Strict Playwright | PASS | 2 passed |
| Aggregate coverage | PASS | 87%; 229 passed, 2 skipped |
| Module coverage gate | PASS | Thresholds satisfied |
| Bandit | PASS | No findings |
| `pip-audit` | PASS | No known vulnerabilities |
| Gitleaks | PASS | No leaks found in the validated history |
| Lychee link validation | PASS | 162 links OK, 0 errors |

Commands used included:

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
lychee --config .tmp-lychee-empty.toml --no-progress README.md docs/**/*.md CHANGELOG.md SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md --exclude-path docs/history/** --exclude-path archive/**
```

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

Run the targeted symlink regression on Linux, WSL with working symlink support, or a Linux container/runner:

```bash
pytest server/tests/test_live_files.py::test_live_file_symlink_escape_blocked_for_read_and_write -q -rA
```

Required result:

- the test executes rather than skips;
- read and write attempts through an escaping symlink are rejected;
- the result is recorded against the final release candidate.

### 2. Hosted GitHub Actions startup failure

Current `CI` and `Commitlint` pull-request runs end in `startup_failure` before any jobs are created.

The repository owner must verify **Settings → Actions → General**, including:

- whether Actions are enabled;
- owner or organization action restrictions;
- selected-action allowlists;
- full-length SHA pinning requirements;
- reusable-workflow restrictions.

Workflow-file changes are not proven effective until jobs are created and normal step logs exist. Do not configure required status checks until both workflows run successfully and reliably.

### 3. Final-HEAD validation

After all release PRs are merged:

1. record the final `main` SHA;
2. rerun pre-commit and `git diff --check`;
3. rerun documentation link validation;
4. rerun full-history Gitleaks against final HEAD;
5. rerun any application/security checks affected by code, dependency, or workflow changes;
6. confirm no release-blocking PRs remain;
7. verify branch protection or ruleset configuration;
8. update this audit with the final evidence.

## Owner-Controlled Publication Steps

Before changing visibility:

- resolve the remaining blockers above;
- confirm Dependabot configuration and security-update settings;
- verify repository description, topics, license detection, and social preview;
- protect `main` against force pushes and deletion;
- require pull requests and conversation resolution;
- add required checks only after hosted checks are healthy.

After publication, enable or verify CodeQL Default Setup, Secret Protection, and Push Protection when available. Review initial alerts before treating those services as clean.

## Final Verdict

Switchboard's implementation, local quality gates, security controls, documentation, canonical license, and visual evidence are substantially ready for a public showcase.

Publication is not yet authorized because:

- Linux symlink-containment validation has not executed successfully;
- hosted Actions still fail before jobs are created;
- final-HEAD validation and repository protection settings remain outstanding.

```text
KEEP PRIVATE - NEAR READY
```
