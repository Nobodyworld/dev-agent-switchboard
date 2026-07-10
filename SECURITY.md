# Security Policy

## Supported Versions

Security fixes are applied to the `main` branch. This repository does not currently promise support for older snapshots or unmaintained releases.

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability or credential exposure.

Use the repository's private GitHub Security Advisory flow when it is available. Include:

- a description of the vulnerability and likely impact;
- affected components or versions;
- reproduction steps or a minimal proof of concept;
- known mitigations or workarounds;
- whether the issue is believed to be actively exploited.

If private advisory reporting is unavailable, contact the maintainer privately through GitHub without posting exploit details, credentials, or personal information in a public channel.

Reports are reviewed on a best-effort basis according to severity and maintainer availability. No fixed acknowledgment, remediation, or disclosure timeline is guaranteed.

## Deployment Posture

Switchboard is intended for controlled agent-coordination environments. A local demonstration configuration must not be treated as production-safe.

Before exposing the service beyond localhost or a trusted network:

- set a strong, randomly generated `SWITCHBOARD_ADMIN_TOKEN`;
- use TLS, a reverse proxy, and network access controls;
- keep `FILES_ROOT` within the intended storage boundary;
- configure `SWITCHBOARD_MAX_LIVE_FILE_BYTES` appropriately;
- validate symlink containment on the target operating system;
- protect environment variables and deployment credentials;
- run the documented release and dependency-security checks.

## Implemented Controls

The repository includes controls and tests for:

- admin-token protection on privileged mutations;
- live-file path containment;
- upload-size enforcement;
- lease ownership, expiry, and heartbeat behavior;
- concurrent checkout rejection;
- rate limiting;
- security and dependency scanning in the release workflow.

Implementation alone is not a deployment guarantee. Review [PUBLIC_RELEASE_AUDIT.md](PUBLIC_RELEASE_AUDIT.md) for the current candidate's executed validation and unresolved environment blockers.

## Coordinated Disclosure

Please allow reasonable time for investigation and remediation before public disclosure. Timing will depend on severity, exploitability, maintainer availability, and whether a safe patch or mitigation is ready.

## Patch Process

1. Reproduce and confirm the issue.
2. Assess severity, affected surfaces, and immediate mitigations.
3. Develop a focused fix and regression tests.
4. Run the relevant local and clean-clone quality/security gates.
5. Publish remediation guidance or release notes when appropriate.
6. Credit reporters who request acknowledgment, unless doing so would create additional risk.

## Dependency Security

[docs/dependencies.md](docs/dependencies.md) records the server and Python-client dependency surface. Vulnerability reports involving third-party packages should identify the package, affected version, and relevant advisory when known.

Release validation includes `pip-audit`, Bandit, Gitleaks, and the repository's broader quality gates. These controls complement, but do not replace, GitHub CodeQL or Secret Protection when those services are available.
