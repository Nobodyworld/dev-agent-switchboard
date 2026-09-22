# Security Policy

## Archived status

```text
ARCHIVED REFERENCE IMPLEMENTATION — NOT PRODUCTION READY
```

Active development and security maintenance have ended. **No versions of Switchboard are currently supported for production use**, and no remediation timeline or future security release is promised.

Do not deploy this repository as an internet-facing, untrusted multi-tenant, or production service.

## Reporting sensitive findings

Do not publish credentials, private data, or weaponized exploit details in a public issue.

If GitHub private vulnerability reporting is available and you believe a finding is important to the historical record, you may use that channel. Reports are handled on a best-effort basis only; archival status means a patch or release should not be expected.

## Final known security boundary

The final codebase contains meaningful controls developed during the project, including:

- administrator-token protection for privileged mutations;
- worker credentials bound to one worker identity, with explicit issuance, rotation, and revocation;
- worker-only API routes and authoritative run/lease ownership checks;
- verifier-only credential persistence and process-private worker secrets;
- live-file path containment and upload-size enforcement;
- lease ownership/expiry behavior and concurrent checkout controls;
- exact-SHA work orders, immutable reviewed manifests, bounded evidence, and process cleanup checks.

Those controls are **not** equivalent to an operating-system sandbox.

The project explicitly stopped before accepting a complete OS-backed isolation mode. In particular, worker credential scope does not isolate OS identities, filesystems, unrelated host credentials, networks, or every process-escape mechanism. Cooperative repository read-only policy and process-tree containment must not be represented as stronger boundaries than they are.

## Historical validation

Historical security validation included Bandit, dependency auditing, Gitleaks, secret scanning, type checks, browser tests, and targeted containment/credential regressions. Those results apply only to the exact revisions and environments recorded in the associated pull requests, ExecPlans, and audits.

See:

- [HISTORY.md](HISTORY.md)
- [archive status](docs/reports/status.md)
- [PUBLIC_RELEASE_AUDIT.md](PUBLIC_RELEASE_AUDIT.md)
- [worker credential operations](docs/operations/worker-credentials.md)

Public source availability is for inspection and historical reference; it is not a continuing security warranty.
