# Public Release Audit — Final Candidate

Status: COMPLETE WITH ONE ENVIRONMENT BLOCKER
Candidate SHA (validated in clean clone): `a143e1a6a4187f648fe9c58c340215af9d11c51d`
Audit date: 2026-07-01
Branch: main
Repository: Nobodyworld/dev-agent-switchboard
Validation authority: local clean-clone execution (GitHub Actions disabled)

---

## Scope

This audit records objective validation results for exactly one implementation candidate:

- `a143e1a6a4187f648fe9c58c340215af9d11c51d`

Historical runs from older commits are intentionally excluded from readiness determination.

---

## Governance, Licensing, and Publication Artifacts

- LICENSE is canonical Apache 2.0 text and complete.
- NOTICE exists and includes project attribution.
- Security and contributor docs are aligned to private-maintainer workflow and local/clean-clone validation authority.
- Public screenshot artifact is present at `docs/assets/switchboard-dashboard.png`.

Status: PASS

---

## Release Gates (Clean Clone)

Environment:

- Clean clone path: `C:\Users\Nobod\Documents\GitHub\dev-agent-switchboard-clean-5d56480`
- Python: 3.11.14 (`.venv`)

Results:

1. `python -m pip check`

- Result: PASS (`No broken requirements found.`)

2. `python -m pre_commit run --all-files --show-diff-on-failure`

- Result: PASS (all hooks passed, no file mutations)

3. `ruff check server client scripts tests web switchboard_cli.py switchboard_client.py`

- Result: PASS (`All checks passed!`)

4. `black --check server client scripts tests web switchboard_cli.py switchboard_client.py`

- Result: PASS (`2 files would be left unchanged.`)

5. `mypy --config-file mypy.ini server client scripts`

- Result: PASS (`Success: no issues found in 119 source files`)

6. `pytest -q`

- Result: PASS (`229 passed, 2 skipped, 5 warnings`)

7. `SWITCHBOARD_STRICT_PLAYWRIGHT=1 pytest web/tests/test_ui.py -rA`

- Result: PASS (`2 passed`)

8. `pytest --cov=server --cov=client --cov=scripts --cov-report=term-missing --cov-report=json:reports/coverage.json -q`

- Result: PASS (`TOTAL 87%`, `229 passed, 2 skipped`)

9. `python scripts/dev.py coverage-gate --json reports/coverage.json`

- Result: PASS (`Coverage thresholds satisfied`)

10. `python -m bandit -q -r server -x server/tests`

- Result: PASS (no findings output)

11. `python -m pip_audit --progress-spinner=off -r server/requirements-dev.txt`

- Result: PASS (`No known vulnerabilities found`)

12. `gitleaks detect --verbose --report-format json --report-path reports/gitleaks.json`

- Result: PASS (`no leaks found`)
- Metadata: `gitleaks 8.30.1`, root commit `3cbda532039bb22b5dcd1cbffbf4c79864db9e29`, `132 commits scanned`

13. `lychee --config .tmp-lychee-empty.toml --no-progress README.md docs/**/*.md CHANGELOG.md SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md --exclude-path docs/history/** --exclude-path archive/**`

- Result: PASS (`162 OK, 0 Errors`)

Release gate summary: PASS

---

## Security Model Evidence (Required Controls)

Targeted validation command:

`pytest server/tests/test_tasks.py::test_health server/tests/test_health.py::test_health_ready_reports_dependencies server/tests/test_websocket_plan.py::test_websocket_plan_demonstrates_two_agent_dependency_flow server/tests/test_live_files.py::test_live_file_write_requires_configured_admin_token server/tests/test_live_files.py::test_live_file_write_rejects_body_over_configured_limit server/tests/test_live_files.py::test_live_file_symlink_escape_blocked_for_read_and_write server/tests/test_rate_limit.py::test_rate_limit_enforced -q -rA`

Result:

- `6 passed, 1 skipped`

Control mapping:

1. Health/live endpoint behavior: PASS (`test_tasks.py::test_health`)
2. Readiness dependencies: PASS (`test_health.py::test_health_ready_reports_dependencies`)
3. Two-agent dependency flow and updates: PASS (`test_websocket_plan.py::test_websocket_plan_demonstrates_two_agent_dependency_flow`)
4. Admin-token mutation protection: PASS (`test_live_files.py::test_live_file_write_requires_configured_admin_token`)
5. Upload-size enforcement: PASS (`test_live_files.py::test_live_file_write_rejects_body_over_configured_limit`)
6. Rate limiting: PASS (`test_rate_limit.py::test_rate_limit_enforced`)
7. Symlink traversal prevention: SKIPPED ON WINDOWS (see blocker section)

---

## Linux Symlink Validation Blocker (Objective)

Observed environment evidence:

- `wsl --list --verbose` reports `Ubuntu` distro present but state is `Stopped`.
- `docker` is not available in PATH (`The term 'docker' is not recognized ...`).
- Windows symlink test skip in clean clone:
  - `SKIPPED ... symlink creation unavailable: [WinError 1314] A required privilege is not held by the client`

Conclusion:

- Linux-only symlink verification could not be executed in this environment due to unavailable Linux/container runtime path and Windows privilege constraints.
- This is a genuine technical blocker external to repository code.

---

## Final Classification

KEEP PRIVATE - NEAR READY

Reason:

- All release gates and required security behaviors that are executable in the current environment passed for candidate `a143e1a6a4187f648fe9c58c340215af9d11c51d`.
- One remaining blocker exists: Linux symlink validation could not be executed due to environment/runtime limitations (WSL/container unavailability and Windows symlink privilege restriction).

Publication verdict:

- Do not publish until Linux symlink validation is executed in a capable environment and recorded against final HEAD.
