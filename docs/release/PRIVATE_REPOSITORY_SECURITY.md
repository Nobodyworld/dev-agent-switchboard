# Private-Repository Security and Publication Controls

**Status:** Pre-publication controls documented  
**Repository:** `Nobodyworld/dev-agent-switchboard`  
**Audit date:** 2026-07-10

This document records security automation available while the repository remains private and owner-controlled steps that must be verified before and after publication. It is separate from `PUBLIC_RELEASE_AUDIT.md`, which remains the authoritative release-readiness record.

## Current posture

The repository is private. CodeQL, GitHub Secret Protection, and Push Protection are deferred until the repository is public or eligible private-repository licensing is available.

```text
CodeQL: DEFERRED UNTIL PUBLIC OR LICENSED
GitHub Secret Protection: DEFERRED UNTIL PUBLIC OR LICENSED
Push Protection: DEFERRED UNTIL PUBLIC OR LICENSED
```

No checked-in CodeQL workflow is required while this deferral remains in effect. Prefer CodeQL Default Setup after publication unless a repository-specific need for Advanced Setup is documented.

## Dependabot coverage

Configuration: `.github/dependabot.yml`

| Ecosystem | Location | Schedule | Open PR limit |
|---|---|---|---:|
| pip | `/server`, `/client/python` | Weekly | 3 |
| Docker | `/server` | Weekly | 2 |
| GitHub Actions | `/` | Weekly | 2 |

Minor and patch updates are grouped. Major updates remain separate. No dependency auto-merge is configured.

The Python client is included because `client/python/pyproject.toml` contains shipped dependency surface, including `requests>=2.31`.

## GitHub Actions disposition

The earlier repository-wide `startup_failure` is resolved by the workflow hardening merged in PR #94.

Successful proof runs:

- Commitlint run `29121887721`: success;
- CI run `29121887745`: success;
- CI jobs: lint, typecheck, test, security, Secrets audit, Link check, Coverage, and Browser UI tests.

The repaired workflows:

- use only read-only repository permissions;
- pin retained GitHub-owned actions to full commit SHAs;
- disable checkout credential persistence;
- replace blocked third-party actions with fixed-version command-line tools;
- fetch full history only where Gitleaks requires it.

Before configuring required checks, confirm the same workflows remain reliable on the final documentation and dependency pull requests and on final `main`.

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

The workflow repair produced a successful hosted full-history Gitleaks job. Publication still requires a final scan against the final merged `main` SHA.

Examples and fixtures must use unmistakably fake values. Review should continue to focus on:

- admin and bearer tokens;
- authorization headers;
- private keys and cloud credentials;
- database URLs;
- environment files;
- logs and reports;
- uploaded file fixtures;
- webhook secrets.

## Owner actions before publication

1. Merge and validate the remaining release PRs through the repaired workflows.
2. Execute the Linux symlink-containment regression without a skip.
3. Run the complete clean-clone validation suite against final `main`.
4. Confirm Dependabot recognizes the new configuration.
5. Enable Dependabot alerts and security updates where available.
6. Configure branch protection or a ruleset after final check names are confirmed.
7. Block force pushes and deletion of `main`.
8. Confirm repository license detection, public documentation, topics, description, and social preview.
9. Run a final full-history secret scan.

## Owner actions after publication

### CodeQL

1. Open **Settings → Advanced Security**.
2. Enable CodeQL Default Setup.
3. Confirm Python is detected.
4. Wait for the initial successful analysis.
5. Review alerts before adding CodeQL as a required check.
6. Avoid duplicate Default and Advanced Setup analyses.

### Secret Protection and Push Protection

1. Enable or verify secret scanning/Secret Protection.
2. Review historical alerts.
3. Revoke and replace any real credential before dismissing an alert.
4. Enable Push Protection when available.
5. Restrict bypass permissions.
6. Never test protection with a real credential.

## Publication gate

This document does not authorize publication. The final release decision belongs in `PUBLIC_RELEASE_AUDIT.md` and must reference the final `main` SHA, final hosted runs, Linux symlink evidence, repository protection settings, and current clean-clone validation.
