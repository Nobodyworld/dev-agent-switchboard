# Private-Repository Security and Publication Controls

**Status:** Pre-publication controls documented  
**Repository:** `Nobodyworld/dev-agent-switchboard`  
**Audit date:** 2026-07-10

This document records security automation that is available while the repository remains private and the owner-controlled steps that must be verified before and after publication. It is intentionally separate from `PUBLIC_RELEASE_AUDIT.md`, which remains the authoritative broader release-readiness record.

## Scope

This note covers:

- Dependabot version-update coverage;
- GitHub Actions policy and startup-failure disposition;
- CodeQL, Secret Protection, and Push Protection deferral;
- local substitute controls;
- publication-time owner actions.

It does not claim that the application is ready for public release, that hosted CI is healthy, or that repository settings have been configured.

## Current private-repository posture

The repository is private. CodeQL, GitHub Secret Protection, and Push Protection are deferred until the repository is public or eligible private-repository licensing is available.

```text
CodeQL: DEFERRED UNTIL PUBLIC OR LICENSED
GitHub Secret Protection: DEFERRED UNTIL PUBLIC OR LICENSED
Push Protection: DEFERRED UNTIL PUBLIC OR LICENSED
```

No checked-in CodeQL workflow is required while this deferral remains in effect. Default Setup should be preferred after publication unless a repository-specific need for Advanced Setup is documented.

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

The current hosted `CI` and `Commitlint` runs end with `startup_failure` before any jobs are created. Workflow-file changes alone have not resolved that condition.

Before relying on hosted checks, the repository owner must verify **Settings → Actions → General**, including:

1. whether Actions are enabled for the repository;
2. whether an owner or organization policy restricts permitted actions;
3. whether only GitHub-owned or explicitly selected actions are allowed;
4. whether action references must use full-length commit SHAs;
5. whether reusable workflows or other policy controls apply.

A successful repair requires both workflows to create jobs and produce normal step logs. A run that ends in `startup_failure` with zero jobs is not a passing or usable validation signal.

Do not configure required status checks until both workflows have completed successfully and reliably on a pull request.

## Local substitute controls

While hosted security features or Actions are unavailable, release validation should include:

- Ruff and formatting checks;
- configured Mypy checks;
- complete pytest execution;
- strict Playwright execution without skips;
- coverage enforcement;
- Bandit;
- `pip-audit` against the declared development requirements;
- full-history Gitleaks;
- documentation link validation;
- Docker build validation when Docker is presented as supported;
- `actionlint` when available.

These controls complement one another. Bandit, Mypy, dependency auditing, and Gitleaks are not substitutes for CodeQL or GitHub Secret Protection.

## Secret-history evidence

The security-deferral workstream recorded a full-history Gitleaks scan using version 8.30.1 with zero findings and zero false positives. That result applies to the audited branch state at the time it was run; publication still requires a fresh scan against the final merged `main` SHA.

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

1. Resolve the Actions startup failure and obtain successful `CI` and `Commitlint` runs.
2. Run the complete clean-clone validation suite against final `main`.
3. Confirm Dependabot configuration is recognized.
4. Enable Dependabot alerts and security updates where available.
5. Configure branch protection or a ruleset only after checks are healthy.
6. Confirm force pushes and branch deletion are blocked on `main`.
7. Confirm the repository license, public documentation, topics, description, and social preview are correct.
8. Run a final full-history secret scan.

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

This document is complete when the owner-controlled settings have been verified, but it does not by itself authorize publication. The final release decision belongs in `PUBLIC_RELEASE_AUDIT.md` and must reference the final `main` SHA and current validation results.
