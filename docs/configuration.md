# Switchboard Configuration Surfaces

Switchboard now exposes a dedicated configuration snapshot across the API, CLI, and operator UI. These views consolidate rate limiter settings, lease durations, extensions, storage health, database wiring, and selected environment metadata so operators and agents can verify runtime posture without digging through source code or database tables.

## API: `/api/configuration`

The FastAPI application serves a typed `ConfigurationResponse` at `GET /api/configuration`. The payload includes:

- `settings`: the existing `SettingsResponse` (rate limit, lease, extensions).
- `admin`: whether an administrative token is configured (token values are never returned).
- `storage`: the live file store root, existence and writeability checks, and disk usage.
- `database`: a password-free connection URL, driver name, and declared engine options.
- `runtime`: the standard runtime snapshot used by diagnostics.
- `environment`: sanitised environment variables and derived defaults for transparency.
- `warnings`: actionable notes (for example, unwritable storage or low disk space).

All sensitive fields (such as `DATABASE_URL` credentials or `SWITCHBOARD_ADMIN_TOKEN`) remain redacted.

## Outbound GitHub adapter

The manual exact-PR adapter uses server-only environment configuration:

- `SWITCHBOARD_GITHUB_TOKEN` — required fine-grained PAT with no default;
- `SWITCHBOARD_GITHUB_API_URL` — optional HTTPS API base, defaulting exactly to
  `https://api.github.com`;
- `SWITCHBOARD_OPERATOR_ID` — optional bounded operator identity, defaulting to
  `local-operator`.

The token requires repository **Metadata: read** and **Pull requests: read and
write**. It is deliberately absent from the configuration API, CLI, and UI,
including configured/unconfigured indicators, and is never forwarded to local
workers. The adapter resolves the credential's stable actor identity before
creating a request, binds it into deterministic request identity and managed
comment ownership, and never exposes that ownership identity through the
configuration surface. See
[GitHub exact pull-request validation](operations/github-exact-pr-validation.md)
for the complete operator and security contract.

## Exact evidence reuse

Evidence reuse has no global environment-variable switch and no
caller-selected cache location. It is chosen per work order with
`reuse_policy`: `never` (default), `allow_exact`, or `require_exact`. The server
derives and persists the execution-policy hash; the assigned worker derives the
environment and dependency-lock portions of the strict identity from its
current exact-SHA checkout.

Local proof uses the existing worker-owned `evidence_root`, retention days, and
artifact count/byte limits. Candidate metadata never contains the configured
root or a local directory. Reuse does not extend the source run's retention;
operators must provision retention long enough for their intended validation
window and accept that pruning or changed bytes make a candidate unavailable.

## CLI: `switchboard-cli config`

The Python CLI gains a `config` subcommand:

```bash
$ switchboard-cli config --base http://localhost:8000 --agent config-cli
```

- Fetches the configuration snapshot without registering the agent.
- Supports `--json` for automation pipelines.
- Prints human-readable summaries of rate limits, storage state, database source, and warnings.

The new `make config` target shells the command with repository defaults so developers can run a single command during local diagnostics.

## Operator UI

The web console now renders a **Configuration** card near the top of the dashboard:

- Displays rate limiter status, lease duration, extension counts, storage metadata, and database provenance.
- Highlights administrative token configuration and the expected `X-Switchboard-Admin-Token` header alongside the backing environment variable.
- Presents runtime metadata (version, environment, commit SHA, uptime, PID) with a one-click copy control for the commit hash.
- Streams sanitised environment variables in a tabular view.
- Surfaces warnings inline with amber styling.
- Provides copy affordances for the live file root and runtime commit for quick sharing in incident channels.

Data refreshes when the page loads and can be reloaded manually using the **Refresh** button.

## Automation Notes

- The configuration service caches values internally and recalculates on demand via existing reload helpers.
- Tests cover the service, API endpoint, and CLI command; front-end coverage relies on integration smoke tests.
- Low disk space detection currently warns at 256 MiB of free space, and the service emits alerts if disk usage cannot be inspected or the storage parent is not writable. Adjust `LOW_STORAGE_THRESHOLD_BYTES` in `server/application/configuration_service.py` if deployments require a different guardrail.

## Future Work

- TODO(P2, 2d) - Extend the configuration payload with database pool utilisation once observability metrics expose the data.
- TODO(P3, 1d) - Persist user-selected configuration refresh cadence in local storage for the operator UI.
