# Public Release Audit - Private-Repository Security Hardening Addendum

Status: IN REVIEW (private-repository feature deferral policy applied)
Audit date: 2026-07-03
Branch audited: security-private-deferral
Repository: Nobodyworld/dev-agent-switchboard
Base reference for this branch: origin/main

This addendum is limited to security-automation hardening context:

- Actions hardening context
- Dependabot configuration
- CodeQL Default Setup compatibility review
- Secret Protection and Push Protection deferral while private
- local substitute controls and Gitleaks evidence
- owner-only activation steps for publication

It does not claim broad public-release readiness for unrelated release-preparation workstreams.

## GitHub Feature Availability (Private Repository)

The repository is currently private and is not covered by GitHub Code Security or GitHub Secret Protection for private repositories.

```text
CodeQL: DEFERRED UNTIL PUBLIC OR LICENSED
GitHub Secret Protection: DEFERRED UNTIL PUBLIC OR LICENSED
Push Protection: DEFERRED UNTIL PUBLIC OR LICENSED
```

This is an account-plan and repository-visibility constraint, not a repository defect or validation failure.

## Active CodeQL Configuration Inspection

Commands executed:

```powershell
Get-ChildItem .github -Recurse -File
git grep -n -E "github/codeql-action|codeql-action|security-events:[[:space:]]*write|CodeQL"
```

Observed:

- `.github/workflows/` contains `ci.yml` and `commitlint.yml`.
- No `.github/workflows/codeql.yml` is present.
- No active `github/codeql-action`, `codeql-action`, or `security-events: write` configuration exists.

Private constraints respected:

- No CodeQL enablement performed.
- No Code Security enablement attempted.
- No active CodeQL workflow created.
- No `security-events: write` permission added.
- No CodeQL execution claimed.

## CodeQL Compatibility Review (Execution Deferred)

```text
CodeQL Default Setup compatibility: REVIEWED
CodeQL execution: NOT AVAILABLE WHILE PRIVATE
Activation: DEFERRED UNTIL PUBLIC OR LICENSED
```

Compatibility assessment:

- Primary detected language: Python.
- Layout is conventional for default detection (`server/`, `client/python/`, `scripts/`, `tests/`).
- Candidate future exclusions after publication: `.venv/`, `__pycache__/`, `reports/`, `storage/files/`, historical/archive artifacts as needed.
- No custom build is required for Python Default Setup.
- No checked-in advanced CodeQL configuration conflicts with Default Setup.
- GitHub Actions must be enabled before Default Setup can run.

No CodeQL scan was executed.

## Local Controls While CodeQL Is Deferred

Active complementary controls:

- Ruff
- configured Mypy
- Bandit
- pip-audit
- complete pytest
- coverage enforcement
- strict Playwright validation
- actionlint (tool probe performed in this audit)
- Docker build validation (host probe performed in this audit)
- full-history Gitleaks
- dependency review via manifests and Dependabot configuration

Bandit and Mypy are complementary static-analysis controls and are not equivalent to CodeQL.

## Secret Protection While Private

```text
GitHub Secret Protection: DEFERRED UNTIL PUBLIC OR LICENSED
GitHub Push Protection: DEFERRED UNTIL PUBLIC OR LICENSED
Current substitute control: full-history Gitleaks plus local secret scanning
```

No attempt was made to enable GitHub Secret Protection or Push Protection while private.

## Secret-History Evidence

Scope and command:

- Full history scan command: `gitleaks detect --verbose --report-format json --report-path reports/gitleaks.json`

Evidence (current branch state):

- Gitleaks version: 8.30.1
- Root commit: `3cbda532039bb22b5dcd1cbffbf4c79864db9e29`
- Audit-branch HEAD at scan time: recorded in command output for this audit run.
- Findings: 0
- False positives: 0
- Final result: no leaks found

Manual inspection focus areas retained:

- SWITCHBOARD_ADMIN_TOKEN
- Authorization headers
- Bearer tokens
- database URLs
- environment files
- uploaded test files
- live-file fixtures
- JUnit reports
- coverage reports
- application logs
- debug output
- temporary scripts
- private keys
- GitHub tokens
- cloud credentials
- webhook secrets

All examples must use unmistakably fake values.

## Dependabot (Active, Not Deferred)

Configuration location:

- `.github/dependabot.yml`

Configured ecosystems and directories:

- `pip` at `/server`
- `docker` at `/server`
- `github-actions` at `/`

Policy checks:

- `version: 2`
- weekly schedules configured
- pip open PR limit: 3
- docker open PR limit: 2
- github-actions open PR limit: 2
- minor/patch grouping configured
- majors left separate by not grouping `major` updates
- no auto-merge configured
- no self-hosted runner configuration present

Owner-only controls remain separate:

- Dependabot alerts
- Dependabot security updates

## Owner-Only Activation Steps After Publication

Do not perform these steps during this private-repository audit.

### A. Confirm GitHub Actions policy

1. Open repository Settings.
2. Open Actions -> General.
3. Confirm Actions are enabled.
4. Apply approved external-action allowlist.
5. Confirm workflows remain read-only and SHA-pinned.

### B. Enable CodeQL Default Setup

1. Settings -> Advanced Security.
2. Code Security -> CodeQL analysis -> Set up.
3. Choose Default.
4. Confirm Python detection.
5. Enable CodeQL.
6. Wait for initial successful run.
7. Confirm alerts and expected analysis coverage.

Do not add a checked-in CodeQL workflow unless Default Setup later proves insufficient for a documented repository-specific reason.

### C. Configure post-activation CodeQL options

1. Enable Copilot Autofix when available.
2. Set failure threshold to High or higher.
3. Set PR alert scope to Only errors where available.
4. Confirm no obsolete advanced CodeQL workflow remains active.
5. Confirm no duplicate CodeQL analyses run.

### D. Verify Secret Protection after publication

1. Settings -> Advanced Security.
2. Confirm secret scanning/Secret Protection is enabled.
3. Review historical alerts.
4. Revoke and replace any real credential before dismissing alerts.
5. Document fixture/false-positive dismissals.

### E. Enable Push Protection after publication

1. Settings -> Advanced Security -> Secret Protection.
2. Confirm secret scanning is enabled.
3. Enable Push protection.
4. Confirm supported patterns are blocked.
5. Restrict bypass permissions.
6. Do not test with real credentials.

## Revised Manual Owner-Settings Report

| Setting | Current audit classification |
|---|---|
| GitHub Actions policy and allowlist | Owner action; do not change |
| Dependabot alerts | Owner action; enable or verify separately |
| Dependabot security updates | Owner action; enable or verify separately |
| CodeQL Default Setup | DEFERRED UNTIL PUBLIC OR LICENSED |
| Copilot Autofix | DEFERRED UNTIL CODEQL IS ACTIVE |
| High-or-higher CodeQL threshold | DEFERRED UNTIL CODEQL IS ACTIVE |
| Only-errors PR alert scope | DEFERRED UNTIL CODEQL IS ACTIVE |
| GitHub Secret Protection | DEFERRED UNTIL PUBLIC OR LICENSED |
| Push Protection | DEFERRED UNTIL PUBLIC OR LICENSED |

## Validation Notes For This Branch

- actionlint: NOT RUN — Go unavailable and actionlint unavailable on host after probing.
- Docker build: NOT RUN — docker CLI unavailable on host after probing.

## Final Report Statement

The repository is currently private and is not covered by GitHub Code Security
or GitHub Secret Protection for private repositories. No CodeQL or GitHub Secret
Protection feature was enabled, and no active CodeQL workflow was added.

CodeQL Default Setup compatibility was reviewed for the Python repository.
CodeQL, Secret Protection, and push protection are deferred until the repository
is public or eligible licensing is added.

Local static analysis, dependency auditing, full-history Gitleaks scanning, and
workflow hardening remain active release requirements.

The branch may be classified as ready to merge after review when:

- workflow hardening passes
- Dependabot configuration is valid
- local static and security gates pass
- full-history Gitleaks passes
- Docker and actionlint validation pass (in an environment where tools are available)
- no active CodeQL workflow remains
- publication activation steps are documented accurately
