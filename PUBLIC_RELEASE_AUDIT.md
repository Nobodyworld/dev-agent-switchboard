# Public Developer Preview Audit — Formal Release Still Blocked

**Classification:** `PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY`
**Current main SHA before this status-only change:** `1dbd939854ab287430d1d9c24865e7ad51cbc29c`
**Public visibility disposition:** `ALLOWED FOR SOURCE PUBLICATION`
**Formal release authorization:** `BLOCKED`
**Production deployment authorization:** `NOT AUTHORIZED`
**Audit updated:** 2026-07-13
**Repository:** `Nobodyworld/dev-agent-switchboard`

## Decision Boundaries

This audit distinguishes four separate decisions:

1. **Repository visibility** controls whether the source code can be inspected publicly.
2. **Developer-preview availability** permits local evaluation and use on controlled trusted networks.
3. **Release authorization** determines whether a version, tag, or general-availability release may be published.
4. **Production deployment safety** determines whether the service is supported for untrusted, multi-tenant, or internet-facing operation.

Public repository visibility is allowed for this developer preview. It is not authorization for a production release, version tag, hosted public service, or general-availability claim.

Switchboard is intended for localhost or controlled trusted networks. Untrusted multi-tenant and direct internet-facing deployment are unsupported.

## Current Repository State

The current `main` commit is:

```text
1dbd939854ab287430d1d9c24865e7ad51cbc29c
```

That commit merged the Phase 1 local-execution-broker architecture in PR #115. PR #115 was documentation and planning only; it did not change runtime behavior. Its hosted validation passed Commitlint, lint/pre-commit, typecheck, tests, security, full-history Gitleaks, link validation, coverage, and strict browser UI checks.

Draft PR #116 remains separate from this publication-status change. It must not be merged as part of making the repository public. Its execution-plane implementation and known lint correction remain subject to their own review and CI evidence.

## Scope of This Preview Authorization

The repository may be made public so developers can:

- inspect the source and architecture;
- clone and run the project locally;
- evaluate the agent-coordination model;
- review issues and draft pull requests;
- contribute through the repository's normal review process.

This authorization does not assert that:

- a production release exists;
- the current branch is a release candidate;
- public internet exposure is safe;
- untrusted users may share one deployment;
- the Linux-specific release gate has passed;
- Docker or every supported environment has been fully revalidated against a final release SHA.

## Governance and Showcase Artifacts

- `LICENSE` contains canonical Apache License 2.0 text.
- `NOTICE` contains project attribution.
- `SECURITY.md`, `CONTRIBUTING.md`, and support documentation describe the maintenance and reporting posture.
- A dashboard screenshot is stored at `docs/assets/switchboard-dashboard.png`.
- Architecture, API, configuration, integration, and workflow documentation are present.
- `.github/dependabot.yml` covers server and Python-client dependencies, Docker, and GitHub Actions.
- `docs/release/PRIVATE_REPOSITORY_SECURITY.md` records repository-security controls and post-publication actions.

**Developer-preview status:** sufficient for public source visibility after this documentation change is merged.

## Historical Clean-Clone Evidence

The latest recorded clean-clone implementation audit used Python 3.11.14 and applied to candidate `a143e1a6a4187f648fe9c58c340215af9d11c51d`. Later merged release-documentation, workflow-hardening, Dependabot, audit-correction, and Phase 1 architecture changes did not alter the previously audited runtime behavior.

| Gate                                                          | Result | Recorded evidence                         |
| ------------------------------------------------------------- | ------ | ----------------------------------------- |
| `python -m pip check`                                         | PASS   | No broken requirements found              |
| `python -m pre_commit run --all-files --show-diff-on-failure` | PASS   | All hooks passed; no mutations            |
| Ruff                                                          | PASS   | All checks passed                         |
| Black                                                         | PASS   | No formatting changes required            |
| Mypy                                                          | PASS   | No issues in 119 configured source files  |
| `pytest -q`                                                   | PASS   | 229 passed, 2 skipped, 5 warnings         |
| Strict Playwright                                             | PASS   | 2 passed                                  |
| Aggregate coverage                                            | PASS   | 87%; 229 passed, 2 skipped                |
| Module coverage gate                                          | PASS   | Thresholds satisfied                      |
| Bandit                                                        | PASS   | No findings                               |
| `pip-audit`                                                   | PASS   | No known vulnerabilities                  |
| Gitleaks                                                      | PASS   | No leaks found in the validated history   |
| Lychee link validation                                        | PASS   | 162 links OK, 0 errors                    |

These are historical release-quality signals, not a substitute for final validation against a future release candidate.

## Hosted GitHub Actions Evidence

The repository-wide workflow startup problem was resolved in PR #94. Retained GitHub-owned actions are pinned to full commit SHAs, workflow permissions are read-only, and checkout credential persistence is disabled.

PRs #94, #96, #97, #105, and #115 produced successful hosted Commitlint and CI evidence. The proven matrix includes:

- lint/pre-commit;
- typecheck;
- tests;
- security scanning;
- full-history Gitleaks;
- documentation link validation;
- coverage;
- strict browser UI tests without skips.

After the repository becomes public, manually dispatch `main` CI and rerun PR #116 CI. Confirm that Commitlint and every matrix job create normal public jobs before relying on those workflows as current evidence.

## Security-Control Evidence

Targeted validation has covered:

1. health and readiness behavior;
2. two-agent dependency unlocking and WebSocket updates;
3. admin-token protection for live-file mutations;
4. upload-size enforcement;
5. rate limiting;
6. path-containment behavior;
7. symlink traversal prevention logic.

The previously recorded targeted result was:

```text
6 passed, 1 skipped
```

The skipped test is the Linux symlink-containment regression. The Windows validation environment could not create the required symlink without additional privileges. Code review is not a substitute for executing that test on Linux.

## Formal Release Blockers

### 1. Linux symlink-containment and final local validation

Issue #104 remains the system of record. The required targeted command is:

```bash
pytest server/tests/test_live_files.py::test_live_file_symlink_escape_blocked_for_read_and_write -q -rA
```

For formal release authorization:

- the test must execute rather than skip;
- read and write attempts through an escaping symlink must be rejected;
- the complete validation command set must be recorded against the exact tested release-candidate SHA;
- Docker must build successfully or have a precise documented blocker.

Do not weaken, delete, skip, or xfail this test.

### 2. Final release identity and evidence

A future release decision must:

1. identify an immutable release commit or tag;
2. record Linux symlink and Docker results;
3. record final clean-clone evidence;
4. confirm no release-blocking pull requests remain;
5. update this audit with explicit release authorization.

### 3. Repository protection and public-security settings

Public visibility does not waive repository controls. The owner should verify:

- pull-request-based changes to `main`;
- conversation resolution;
- force-push and branch-deletion protections;
- the intended merge/history policy;
- required checks after normal public jobs are observed;
- Dependabot alerts and security updates;
- repository description, topics, license detection, and social preview.

After publication, enable or verify CodeQL Default Setup, Secret Protection, and Push Protection when available. Review initial alerts before treating those services as clean.

Parent issue #95 tracks the formal release checklist. Issue #104 contains the Linux/local validation handoff and must remain open until the symlink test actually executes and passes.

## Final Verdict

The owner may change repository visibility to public **after this developer-preview status change is merged**, using the classification:

```text
PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
```

That visibility change is limited to public source publication and developer evaluation. Formal release authorization remains blocked by issue #104 and the final release/settings review. Production, untrusted multi-tenant, and direct internet-facing deployment remain unsupported.
