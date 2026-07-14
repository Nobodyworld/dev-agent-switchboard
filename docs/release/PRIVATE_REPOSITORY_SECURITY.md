# Repository Security and Publication Controls

**Status:** Public developer-preview controls documented
**Repository:** `Nobodyworld/dev-agent-switchboard`
**Audit date:** 2026-07-13

This document records repository-security automation and owner-controlled steps before and after public source publication. It is separate from `PUBLIC_RELEASE_AUDIT.md`, which remains the authoritative distinction between public preview, formal release authorization, and production deployment safety.

## Current posture

The repository is approved for public source visibility as a developer preview after the preview-status documentation is merged.

```text
Repository visibility: PUBLIC DEVELOPER PREVIEW ALLOWED
Formal release: BLOCKED
Production deployment: NOT AUTHORIZED
```

Public repository visibility does not authorize a hosted public service. Switchboard is intended for localhost or controlled trusted networks. Untrusted multi-tenant and direct internet-facing deployments are unsupported.

CodeQL, GitHub Secret Protection, and Push Protection should be enabled or verified after publication when available. Prefer CodeQL Default Setup unless a repository-specific need for Advanced Setup is documented.

## Dependabot coverage

Configuration: `.github/dependabot.yml`

| Ecosystem      | Location                    | Schedule | Open PR limit |
| -------------- | --------------------------- | -------- | ------------: |
| pip            | `/server`, `/client/python` | Weekly   |             3 |
| Docker         | `/server`                   | Weekly   |             2 |
| GitHub Actions | `/`                         | Weekly   |             2 |

Minor and patch updates are grouped. Major updates remain separate. No dependency auto-merge is configured.

The Python client is included because `client/python/pyproject.toml` contains shipped dependency surface, including `requests>=2.31`.

## GitHub Actions disposition

The earlier repository-wide `startup_failure` was resolved by the workflow hardening merged in PR #94.

The repaired workflows:

- use read-only repository permissions;
- pin retained GitHub-owned actions to full commit SHAs;
- disable checkout credential persistence;
- replace blocked third-party actions with fixed-version command-line tools;
- fetch full history only where Gitleaks requires it.

Successful hosted proof has included Commitlint, lint, typecheck, tests, security, full-history Gitleaks, link validation, coverage, and strict browser UI execution.

After publication, manually dispatch `main` CI and rerun PR #116 CI. Confirm the expected public jobs are created before adding or updating required-check rules.

## Local and hosted controls

Release validation includes:

- pre-commit, Ruff, and formatting checks;
- configured Mypy checks;
- complete pytest execution;
- strict Playwright execution without skips;
- coverage enforcement;
- Bandit;
- `pip-audit` against declared development requirements;
- full-history Gitleaks;
- documentation link validation;
- Docker build validation when Docker is presented as supported;
- `actionlint` when available.

These controls complement one another. Bandit, Mypy, dependency auditing, and Gitleaks are not substitutes for CodeQL or GitHub Secret Protection.

## Secret-history evidence

PR #115, whose merge commit is the current pre-preview-documentation `main` SHA `1dbd939854ab287430d1d9c24865e7ad51cbc29c`, passed the hosted full-history Gitleaks job. PR #115 changed documentation, planning, and link-check configuration only.

The public-preview documentation branch must also receive a final Gitleaks result when Actions can run normally. Any real credential discovered before or after publication must be revoked and replaced before an alert is dismissed.

Examples and fixtures must use unmistakably fake values. Review should continue to focus on:

- admin and bearer tokens;
- authorization headers;
- private keys and cloud credentials;
- database URLs;
- environment files;
- logs and reports;
- uploaded file fixtures;
- webhook secrets.

## Owner actions before or at public visibility

1. Merge the public developer-preview status documentation.
2. Confirm the repository still points `main` at the expected merged documentation SHA.
3. Confirm the canonical Apache-2.0 license is detected.
4. Verify repository description, topics, and social preview.
5. Confirm Dependabot alerts and security updates are enabled where available.
6. Verify pull-request, conversation-resolution, force-push, and branch-deletion controls for `main`.
7. Keep PR #116 unmerged until its own review and CI correction are complete.
8. Do not expose a running Switchboard service to the public internet.

The Linux symlink-containment test is not a blocker to public source visibility, but it remains a mandatory formal-release gate under issue #104.

## Owner actions after publication

### Public CI confirmation

1. Manually dispatch the `main` CI workflow.
2. Rerun PR #116 CI after its focused correction is pushed.
3. Verify that Commitlint, lint, typecheck, tests, security, Secrets audit, Link check, Coverage, and Browser UI tests create normal jobs.
4. Add or update required checks only after their final public names and behavior are confirmed.

### CodeQL

1. Open **Settings → Advanced Security**.
2. Enable CodeQL Default Setup.
3. Confirm Python is detected.
4. Wait for the initial successful analysis.
5. Review alerts before adding CodeQL as a required check.
6. Avoid duplicate Default and Advanced Setup analyses.

### Secret Protection and Push Protection

1. Enable or verify secret scanning or Secret Protection.
2. Review historical alerts.
3. Revoke and replace any real credential before dismissing an alert.
4. Enable Push Protection when available.
5. Restrict bypass permissions.
6. Never test protection with a real credential.

## Formal release gate

Public source visibility and formal release are separate decisions.

`PUBLIC_RELEASE_AUDIT.md` may permit the repository to be visible as a public developer preview while still withholding release authorization. A production release must reference an immutable release candidate, current validation, Linux symlink evidence, Docker disposition, repository protections, and explicit final authorization.
