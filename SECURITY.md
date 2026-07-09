# Security Policy

## Supported Versions

Security fixes are applied to the `main` branch. If releases are published, prefer the most recent release or the latest reviewed commit on `main`.

## Reporting a Vulnerability

If you discover a security vulnerability, **do not** open a public issue with exploit details, credentials, private logs, or sensitive reproduction data.

Preferred private reporting path:

1. Use the repository's GitHub Security Advisory process when it is available.
2. If advisory reporting is unavailable, contact the maintainer privately through GitHub before sharing sensitive details.
3. Share only the minimum information needed to confirm impact until a private channel is established.

Helpful report details include:

- a description of the vulnerability and potential impact;
- affected version, branch, or commit SHA;
- steps to reproduce or proof-of-concept details;
- known mitigations or workarounds;
- whether a credential, token, or private data may have been exposed.

Maintainer response is best-effort for this showcase/open-source repository. Security reports are prioritized over general support requests.

## Public Security Posture

- Privileged runtime mutations are protected by `SWITCHBOARD_ADMIN_TOKEN` when configured.
- Local demonstrations may run without an admin token; do not treat that mode as safe for shared or exposed deployments.
- Live-file uploads are bounded by `SWITCHBOARD_MAX_LIVE_FILE_BYTES` and should remain inside the configured storage root.
- The default support target is the latest reviewed commit on `main`; older snapshots may not receive fixes.
- Dependency review and local reproduction guidance live in [docs/dependencies.md](docs/dependencies.md).

## Deployment Guidance

Before exposing Switchboard beyond localhost or a trusted network:

- set a strong random `SWITCHBOARD_ADMIN_TOKEN` through environment-specific secret storage;
- avoid printing tokens in logs, reports, or screenshots;
- keep `FILES_ROOT` inside the configured storage boundary;
- validate path-containment behavior on the target operating system;
- configure TLS and network access controls through a reverse proxy or deployment platform;
- review upload limits, rate limits, and database location;
- run current tests and security checks for the branch being deployed.

## Coordinated Disclosure

We request a reasonable private disclosure period to investigate, patch, and document a fix before public details are shared. If the vulnerability is actively exploited or requires urgent attention, we will coordinate an expedited disclosure timeline where possible.

## Patch Process

1. Reproduce and confirm the issue.
2. Develop a fix and corresponding regression tests.
3. Run the relevant local and hosted validation gates available for the branch.
4. Document mitigation or upgrade guidance.
5. Credit reporters who request acknowledgment when a public changelog or advisory is published.

## Dependency Security

The [Dependency & License Audit](docs/dependencies.md) tracks packages used by the server and Python client. When reporting a vulnerability in a third-party library, reference the package name and version or constraint so maintainers can cross-check impact.

Run local dependency checks where supported:

```bash
pip-audit --progress-spinner=off
```

If the repository has active Dependabot configuration or hosted CI at the time of review, use those results as additional evidence. Do not assume a historic scan applies to a new branch or deployment.

## Secret Handling

- Never commit real credentials, tokens, private keys, or production database URLs.
- Use obvious placeholders such as `replace-with-a-random-secret` in examples.
- Prefer environment variables or deployment secret stores for runtime secrets.
- If a real credential is committed or exposed, revoke and rotate it before opening a public issue.

Thank you for helping keep Switchboard secure.