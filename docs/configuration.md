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
