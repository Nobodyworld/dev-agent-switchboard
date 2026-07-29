# Repository Security and Publication Controls

**Status:** Public developer-preview controls documented and technically validated  
**Repository:** `Nobodyworld/dev-agent-switchboard`  
**Last reconciled:** 2026-07-29

This document records repository-security automation and owner-controlled checks after public source publication. It is separate from `PUBLIC_RELEASE_AUDIT.md`, which remains the authoritative distinction between public preview, formal release authorization, and production deployment safety.

## Current posture

```text
Repository visibility: PUBLIC
Classification: PUBLIC DEVELOPER PREVIEW — NOT PRODUCTION READY
Validated source candidate: b79aba1aaf72ffd20f0221bdf0fd77552541073f
Current evidence-bearing main: 8de2fabb6532c274e7a61bad7d2e780e2e6169d8
Formal release: NOT AUTHORIZED
Production deployment: NOT AUTHORIZED
```

Public repository visibility does not authorize a hosted public service. Switchboard is intended for localhost or controlled trusted networks. Untrusted multi-tenant and direct internet-facing deployments are unsupported.

## Connector-verified repository configuration

- The repository is public.
- `main` is the default branch.
- Squash merge is the only enabled merge method.
- Auto-merge is disabled.
- Update-branch support is enabled.
- A canonical Apache License 2.0 file is present.
- `SECURITY.md` directs suspected vulnerabilities to private GitHub reporting.
- Hosted workflows use read-only repository permissions.
- Retained GitHub actions are pinned to full commit SHAs.
- Checkout credential persistence is disabled.

The owner previously confirmed that the `main` protection rule requires pull requests and conversation resolution, blocks force pushes and branch deletion, and selects the public CI checks. PR #116 exercised that protected merge gate successfully.

## Required public checks

The established public check names are:

- `Commitlint`;
- `lint`;
- `typecheck`;
- `test`;
- `security`;
- `Secrets audit`;
- `Link check`;
- `Coverage`;
- `Browser UI tests`.

These names come from `.github/workflows/commitlint.yml` and `.github/workflows/ci.yml` and have produced successful public pull-request jobs.

## Dependabot coverage

Configuration: `.github/dependabot.yml`

| Ecosystem      | Location                    | Schedule | Open PR limit |
| -------------- | --------------------------- | -------- | ------------: |
| pip            | `/server`, `/client/python` | Monthly  |             2 |
| Docker         | `/server`                   | Monthly  |             1 |
| GitHub Actions | `/`                         | Monthly  |             1 |

Minor and patch updates are grouped. Major updates remain separate. No dependency auto-merge is configured.

The Python client is included because `client/python/pyproject.toml` contains shipped dependency surface.

## Executed technical controls

Issue #104 and PR #127 completed the selected release-candidate evidence pass. Recorded gates include:

- Linux symlink-containment execution without a skip;
- clean Python 3.11 dependency installation and `pip check`;
- pre-commit, Ruff, Black, Mypy, and TODO policy;
- complete pytest and strict Playwright execution;
- aggregate and module coverage enforcement;
- Bandit and `pip-audit`;
- full-history Gitleaks;
- documentation link validation;
- exact-candidate Docker build;
- clean candidate and public-hygiene verification.

The evidence is recorded in `PUBLIC_RELEASE_AUDIT.md`. Technical validation does not itself authorize a release or production deployment.

## Remaining owner-controlled GitHub review

The GitHub connector used for this review does not expose these settings or alert inventories directly:

1. Enable or verify CodeQL Default Setup and confirm Python analysis succeeds.
2. Review CodeQL alerts.
3. Review Dependabot alerts and confirm Dependabot security updates are enabled.
4. Review secret-scanning alerts.
5. Enable or verify Secret Protection and Push Protection and restrict bypass permissions.
6. Confirm repository description and topics.
7. Confirm GitHub detects the Apache-2.0 license; the canonical file is already present.
8. Confirm the social preview.
9. Decide explicitly whether to create a developer-preview prerelease or no release.

Avoid duplicate CodeQL Default and Advanced Setup analyses. Never test secret protection with a real credential. Revoke and replace any real credential before dismissing an alert.

## Phase 2 boundary

PR #125 and issues #121/#122 were deliberately excluded from the validated release candidate. PR #125 must be refreshed from current reviewed `main` and fully revalidated before a separate merge decision.

## Formal release boundary

Public source visibility and formal release remain separate decisions. A future prerelease or release must reference an immutable commit, the completed technical evidence, the remaining owner-controlled GitHub review, and explicit owner authorization.

Production, untrusted multi-tenant, and direct internet-facing deployment remain unsupported unless separately designed, reviewed, and authorized.
