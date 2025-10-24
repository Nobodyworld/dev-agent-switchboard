# Security Policy

## Supported Versions

Security fixes are applied to the `main` branch. Please deploy from the latest commit on `main` or the most recent tagged release.

## Reporting a Vulnerability

If you discover a security vulnerability, **do not** open a public issue. Instead, email the Switchboard maintainers at <security@openai.com> with the following information:

- A description of the vulnerability and its potential impact.
- Steps to reproduce the issue or proof-of-concept code.
- Any known mitigations or workarounds.

We aim to acknowledge new reports within two business days. After triage, we will provide regular status updates until the issue is resolved.

## Coordinated Disclosure

We request a 90-day embargo period to investigate, patch, and release a fix. If the vulnerability is actively exploited or requires urgent attention, we will work with you on an expedited disclosure timeline.

## Patch Process

1. Reproduce and confirm the issue.
2. Develop a fix and corresponding regression tests.
3. Run the full CI pipeline, including security scans.
4. Coordinate release notes and deployment guidance.
5. Credit reporters who request acknowledgment in the public changelog.

## Dependency Security

The [Dependency & License Audit](docs/DEPENDENCIES.md) tracks the packages used
by both the server and Python client. When reporting a vulnerability in a
third-party library, please reference the package name and version pinned in
that document so we can cross-check impact quickly. We prioritise updates for
dependencies with known CVEs and will publish mitigation guidance if immediate
upgrades are not possible.

Thank you for helping us keep Switchboard secure.
