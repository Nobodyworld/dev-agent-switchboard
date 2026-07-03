# Security Policy

## Supported Versions

Security fixes are applied to the `main` branch. Please deploy from the latest commit on `main` or the most recent tagged release.

## Reporting a Vulnerability

If you discover a security vulnerability, **do not** open a public issue. Instead, report it privately using [GitHub Security Advisories](https://docs.github.com/en/code-security/security-advisories/repository-security-advisories/about-repository-security-advisories) and include the following information:

- A description of the vulnerability and its potential impact.
- Steps to reproduce the issue or proof-of-concept code.
- Any known mitigations or workarounds.

We aim to acknowledge new reports within two business days. After triage, we will provide regular status updates until the issue is resolved.

## Public Security Posture

- Privileged runtime mutations are protected by `SWITCHBOARD_ADMIN_TOKEN` when configured.
- Live-file uploads are bounded by `SWITCHBOARD_MAX_LIVE_FILE_BYTES` and inherit admin-token protection when enabled.
- The default support target is the latest commit on `main`; older snapshots may not receive fixes.
- Dependency review and local reproduction guidance live in [docs/dependencies.md](docs/dependencies.md).

## Coordinated Disclosure

We request a 90-day embargo period to investigate, patch, and release a fix. If the vulnerability is actively exploited or requires urgent attention, we will work with you on an expedited disclosure timeline.

## Patch Process

1. Reproduce and confirm the issue.
2. Develop a fix and corresponding regression tests.
3. Run the full local quality and security validation suite, including clean-clone checks when hosted Actions are disabled.
4. Coordinate release notes and deployment guidance.
5. Credit reporters who request acknowledgment in the public changelog.

## Dependency Security

The [Dependency & License Audit](docs/dependencies.md) tracks the packages used
by both the server and Python client. When reporting a vulnerability in a
third-party library, please reference the package name and version pinned in
that document so we can cross-check impact quickly. Local validation runs `pip-audit` via `python scripts/dev.py verify` and clean-clone testing, providing authoritative verification when GitHub Actions is disabled. We prioritise updates for dependencies with known CVEs and will publish mitigation guidance if immediate upgrades are not possible.

Thank you for helping us keep Switchboard secure.
